import salabim as sim
import gurobipy as gp
from gurobipy import GRB
from src.models.agv import AGVStatus
from src.models.task import Task
import networkx as nx

from src.config import (BATCH_SIZE, MAX_WAIT_TIME, MAX_BATTERY, MAX_VOLUME, MAX_PAYLOAD, 
                        BATTERY_THRESHOLD, E_BASE, ALPHA)


class ControlSystem(sim.Component):
    def setup(
        self,
        warehouse,
        order_queue,
        available_agvs,
        batch_size=BATCH_SIZE,
        max_wait_time=MAX_WAIT_TIME
    ):
        self.warehouse = warehouse
        self.order_queue = order_queue
        self.available_agvs = available_agvs
        self.batch_size = batch_size
        self.max_wait_time = max_wait_time
        self.agvs = available_agvs
        self.last_batch_time = 0
        self.task_counter = 0

    def _generate_task_id(self):
        self.task_counter += 1
        return self.task_counter

    def process(self):
        # Yieldless state machine: process is called repeatedly upon reactivation
        if len(self.order_queue) == 0:
            self.passivate()
            return
            
        # Check if we should wait for more orders (up to batch_size)
        if len(self.order_queue) < self.batch_size:
            if self.env.now() - self.last_batch_time < self.max_wait_time:
                self.hold(1)
                return

        # Check number of available agvs
        available_agvs = [
            agv for agv in self.agvs
            if agv.status == AGVStatus.IDLE
        ]

        if len(available_agvs) == 0:
            self.passivate()
            return

        # Make a batch of the orders that is waiting to be handled
        batch_orders = list(self.order_queue)[:self.batch_size]

        # Make tasks based on the routing algorithm
        tasks = self.routing_algorithm(
            orders=batch_orders,
            available_agvs=available_agvs
        )

        # Assign task to agv
        for task in tasks:
            agv = task.agv
            agv.current_task = task
            agv.route = task.route
            agv.orders = task.orders
            agv.status = AGVStatus.MOVING
            for order in task.orders:
                order.status = "ASSIGNED"
                order.leave(self.order_queue)
            agv.activate()
            
        self.last_batch_time = self.env.now()
        
        # Hold a tiny amount of time to allow state changes to propagate before next check
        self.hold(0)
    

    #Define the routing algorithm 
    def routing_algorithm(self, orders, available_agvs):
        #As long as there are no orders or no agvs --> return empty (double safety)
        if len(orders) == 0 or len(available_agvs) == 0:
            return []

        # ============================================================
        # Warehouse graph
        # ============================================================

        G = self.warehouse.routing_graph._graph

        N = list(G.nodes)
        A_undir = list(G.edges)

        A = []
        distance = {}

        for i, j in A_undir:
            A.append((i, j))
            A.append((j, i))

            d = G.edges[i, j]["weight"]
            distance[i, j] = d
            distance[j, i] = d

        idle_spot = self.warehouse.idle_spot_node_ids[0]
        packing_station = self.warehouse.packing_station_node_ids[0]

        # ============================================================
        # Orders
        # ============================================================
        #make set of orders
        O = [order.order_id for order in orders]

        #order id
        order_by_id = {
            order.order_id: order
            for order in orders
        }
        #order weight
        Ow = {
            order.order_id: order.item.weight
            for order in orders
        }
        #order volume
        Ov = {
            order.order_id: order.item.volume
            for order in orders
        }
        #order location
        Ol = {
            order.order_id: order.item.node_id
            for order in orders
        }

        
        # ============================================================
        # AGVs
        # ============================================================

        #make set of agvs for routing
        V = [agv.agv_id for agv in available_agvs]

        #agv id
        agv_by_id = {
            agv.agv_id: agv
            for agv in available_agvs
        }

        #battery level of agvs
        AGVb = {
            agv.agv_id: agv.battery
            for agv in available_agvs
        }

        

        # ============================================================
        # Parameters
        # ============================================================

        M = 10000
        BIG_REWARD = 1000000000

        # ============================================================
        # Model
        # ============================================================

        model = gp.Model("AGV_routing")
        model.Params.OutputFlag = 0
        model.Params.NonConvex = 2

        y = model.addVars(O, V, vtype=GRB.BINARY, name="y")                            #order connected to agv
        x = model.addVars(A, V, vtype=GRB.BINARY, name="x")                            # agv drives over edge
        u = model.addVars(V, vtype=GRB.BINARY, name="u")                               #agv is being used
        b = model.addVars(N, V, lb=BATTERY_THRESHOLD, ub=MAX_BATTERY, vtype=GRB.CONTINUOUS, name="b")       #battery level of agv at node
        q = model.addVars(N, V, lb=0, ub=MAX_PAYLOAD, vtype=GRB.CONTINUOUS, name="q")           # weight of orders on an agv at node

        pickup_weight = {
            (n, v): gp.quicksum(
                Ow[o] * y[o, v]
                for o in O
                if Ol[o] == n
            )
            for n in N
            for v in V
        }

        # ============================================================
        # Objective
        # ============================================================

        #minimize the energy consumption (ALPHA * laod + base) times the distance driven for agvs
        model.setObjective(
            gp.quicksum(
                (E_BASE + ALPHA * q[i, v]) * distance[i, j] * x[i, j, v]
                for i, j in A
                for v in V
            )- BIG_REWARD * gp.quicksum(y[o, v] for o in O for v in V),
            GRB.MINIMIZE
        )


        # ============================================================
        # Constraints
        # ============================================================

        #Innovation constraint!! max 1 order = no innovation, when innovation this constraint should be turned off
        # model.addConstrs((
        #     gp.quicksum(y[o, v] for o in O) <= 1
        #     for v in V),
        #     name="max_one_order_per_agv")
        

        # dont exceed weight capacity of an agv
        model.addConstrs(
            (
                gp.quicksum(Ow[o] * y[o, v] for o in O) <= MAX_PAYLOAD
                for v in V
            ),
            name="weight_capacity"
        )

        # dont exceed volume capacity of an agv
        model.addConstrs(
            (
                gp.quicksum(Ov[o] * y[o, v] for o in O) <= MAX_VOLUME
                for v in V
            ),
            name="volume_capacity"
        )

        # if possible all orders handled, otherwise leave in queue but order should be handled not more than 1 time
        model.addConstrs(
            (
                gp.quicksum(y[o, v] for v in V) <= 1
                for o in O
            ),
            name="each_order_at_most_once"
        )

        # each agv should leave idle spot only once when its used
        model.addConstrs(
            (
                gp.quicksum(x[i, j, v] for i, j in A if i == idle_spot) == u[v]
                for v in V
            ),
            name="leave_idle_spot"
        )

        # each agv should arrive at packing station once when its used
        model.addConstrs(
            (
                gp.quicksum(x[i, j, v] for i, j in A if j == packing_station) == u[v]
                for v in V
            ),
            name="arrive_packing_station"
        )

        #when an order is connected to an agv, the agv should be used 
        model.addConstrs(
            (
                y[o, v] <= u[v]
                for o in O
                for v in V
            ),
            name="order_only_if_agv_used"
        )

        # if arrive at node also leave node
        for n in N:
            if n not in [idle_spot, packing_station]:
                for v in V:
                    model.addConstr(
                        gp.quicksum(x[i, j, v] for i, j in A if j == n)
                        ==
                        gp.quicksum(x[i, j, v] for i, j in A if i == n),
                        name=f"flow_{n}_{v}"
                    )

        #when order is assigned, it should visit that shelve
        for o in O:
            node = Ol[o]

            for v in V:
                model.addConstr(
                    gp.quicksum(x[i, j, v] for i, j in A if j == node) >= y[o, v],
                    name=f"visit_order_{o}_{v}"
                )

        # make the start load = 0
        model.addConstrs(
            (
                q[idle_spot, v] == 0
                for v in V
            ),
            name="start_load"
        )

        # load flow 
        model.addConstrs(
            (
                q[j, v] >= q[i, v] + pickup_weight[j, v]
                - MAX_PAYLOAD * (1 - x[i, j, v])
                for i, j in A
                for v in V
            ),
            name="load_flow_lb"
        )

        model.addConstrs(
            (
                q[j, v] <= q[i, v] + pickup_weight[j, v]
                + MAX_PAYLOAD * (1 - x[i, j, v])
                for i, j in A
                for v in V
            ),
            name="load_flow_ub"
        )

        #start battery level
        model.addConstrs(
            (
                b[idle_spot, v] == AGVb[v]
                for v in V
            ),
            name="start_battery"
        )

        # battery flow (These can be turned on if we want to include battery in determination of route but for speed theyre now off)
        # model.addConstrs(
        #     (
        #         b[j, v] <= b[i, v]
        #         - (E_BASE + ALPHA * q[i, v]) * distance[i, j]
        #         + M * (1 - x[i, j, v])
        #         for i, j in A
        #         for v in V
        #     ),
        #     name="battery_flow_ub"
        # )

        # model.addConstrs(
        #     (
        #         b[j, v] >= b[i, v]
        #         - (E_BASE + ALPHA * q[i, v]) * distance[i, j]
        #         - M * (1 - x[i, j, v])
        #         for i, j in A
        #         for v in V
        #     ),
        #     name="battery_flow_lb"
        # )

        # ============================================================
        # Solve
        # ============================================================

        model.optimize()

        if model.status != GRB.OPTIMAL:
            print("No optimal routing solution found.")
            return []

        # ============================================================
        # Create tasks
        # ============================================================

        tasks = []

        for v in V:
            assigned_orders = [
                order_by_id[o]
                for o in O
                if y[o, v].X > 0.5
            ]

            if len(assigned_orders) == 0:
                continue

            active_edges = [
                (i, j)
                for i, j in A
                if x[i, j, v].X > 0.5
            ]

            order_nodes = [
                Ol[o]
                for o in O
                if y[o, v].X > 0.5
            ]
            route_node_ids = [idle_spot]
            current = idle_spot
            for node in order_nodes:
                part = nx.shortest_path(
                    G,
                    current,
                    node,
                    weight="weight"
                )
                route_node_ids += part[1:]
                current = node
            part = nx.shortest_path(
                G,
                current,
                packing_station,
                weight="weight"
            )
            route_node_ids += part[1:]

            selected_agv = agv_by_id[v]

            task = Task(
                task_id=self._generate_task_id(),
                orders=assigned_orders,
                route=route_node_ids,
                agv=selected_agv,
                creation_time=self.env.now()
            )

            tasks.append(task)

        return tasks
