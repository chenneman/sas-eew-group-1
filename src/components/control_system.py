"""
Central control system for the warehouse simulation.
Manages the order queue, dispatches idle AGVs, and uses a Gurobi optimization model
to route AGVs to pick up items efficiently.
"""

import salabim as sim
import gurobipy as gp
from gurobipy import GRB
from src.components.agv import AGVStatus
from src.entities.task import Task

from src.config import (BATCH_SIZE, MAX_WAIT_TIME, MAX_BATTERY, MAX_VOLUME, MAX_PAYLOAD,
                        BATTERY_THRESHOLD, E_BASE, ALPHA, INNOVATION_ENABLED, PICK_TIME_PER_ITEM)


# TODO refactor spaghetti to more functions, add typehints
class ControlSystem(sim.Component):
    """
    The brain of the AGV fleet. Pools incoming orders into batches and uses a Mixed-Integer
    Programming (MIP) model via Gurobi to assign orders and calculate optimal routing paths.
    """
    def setup(
        self,
        warehouse,
        order_queue,
        available_agvs,
        batch_size=BATCH_SIZE,
        max_wait_time=MAX_WAIT_TIME,
        packing_queues_map=None
    ):
        """
        Initializes the ControlSystem component.

        Args:
            warehouse: The Warehouse environment component containing the layout graph.
            order_queue (sim.Queue): The queue containing pending Orders.
            available_agvs (sim.Queue): The queue containing idle AGVs ready for dispatch.
            batch_size (int): The number of orders to pool before triggering a routing run.
            max_wait_time (float): The maximum time (in sim minutes) to wait for a full batch before triggering.
            packing_queues_map (dict): Mapping of packing node IDs to their respective Salabim Queues.
        """
        self.warehouse = warehouse
        self.order_queue = order_queue
        self.available_agvs = available_agvs
        self.batch_size = batch_size
        self.max_wait_time = max_wait_time
        self.packing_queues_map = packing_queues_map or {}
        self.agvs = available_agvs
        self.last_batch_time = 0
        self.task_counter = 0

    def _generate_task_id(self):
        self.task_counter += 1
        return self.task_counter

    def process(self):
        while True:
            # 1. Wait for orders if queue is empty
            if len(self.order_queue) == 0:
                self.passivate()
                continue

            # 2. Wait for AGVs if none are available
            available_agvs = list(self.available_agvs)
            if len(available_agvs) == 0:
                self.passivate()
                continue

            # 3. Handle Batching Logic
            # Check if we have enough orders for a full batch
            if len(self.order_queue) < self.batch_size:
                time_since_last = self.env.now() - self.last_batch_time
                
                # If we haven't reached the timeout yet, wait until the timeout or until interrupted
                if time_since_last < self.max_wait_time:
                    wait_remaining = self.max_wait_time - time_since_last
                    # Salabim's hold can be interrupted by .activate() from OrderGenerator or AGVs
                    self.hold(wait_remaining)
                    # After waking up, re-evaluate conditions (queue might have filled or timeout hit)
                    continue

            # 4. Execute Routing Logic
            # Make a larger batch proportional to the number of available AGVs
            num_available = len(available_agvs)
            max_batch_to_check = num_available * self.batch_size
            batch_orders = list(self.order_queue)[:max_batch_to_check]

            tasks = self.routing_algorithm(
                orders=batch_orders,
                available_agvs=available_agvs
            )

            # 5. Assign tasks
            for task in tasks:
                agv = task.agv
                if agv in self.available_agvs:
                    agv.leave(self.available_agvs)
                
                agv.current_task = task
                agv.route = task.route
                agv.orders = task.orders
                agv.status = AGVStatus.MOVING
                for order in task.orders:
                    order.status = "ASSIGNED"
                    order.assignment_min = self.env.now()
                    self.order_queue.remove(order)
                agv.activate()

            self.last_batch_time = self.env.now()
            # Minimal hold to allow state propagation
            self.hold(0)


    def routing_algorithm(self, orders: list, available_agvs: list) -> list[Task]:
        """
        Executes a Point-of-Interest (POI) based Vehicle Routing Problem (VRP) using Gurobi.

        ALGORITHM OVERVIEW:
        -------------------
        Instead of modeling every individual grid cell in the warehouse as a potential 
        node in the optimization (which leads to ~700 nodes and thousands of variables), 
        this algorithm focuses strictly on the active 'Points of Interest':
        1.  The current locations of available AGVs.
        2.  The shelf locations of items in the current order batch.
        3.  The packing station (dropoff point).

        REASONING:
        ----------
        - Performance: Reduces the optimization search space from ~700 nodes to ~5-15 nodes.
        - Scalability: Fits within restricted Gurobi licenses while solving in milliseconds.
        - Mathematical Equivalence: Since the optimal path between any two points in the
          warehouse grid is a shortest-path (A*), we pre-calculate these paths using 
          NetworkX. The VRP then decides the optimal *sequence* of these POIs to 
          minimize the objective function (Total Energy = Distance * Mass).

        PROCESS:
        --------
        1. Identify POIs: Extract node IDs for AGVs, shelf items, and packing station.
        2. Build Distance Matrix: Use NetworkX A* to pre-calculate shortest-path weights 
           between every pair of POIs.
        3. Formulate MIP: 
           - Variables: Binary edges (x), assignment (y), load (q), and MTZ sequence (u).
           - Objective: Minimize sum((E_BASE + ALPHA * load) * distance) for all chosen edges.
        4. Reconstruct Tasks: Map the optimal POI sequence back to a full grid path and 
           chunk them into actionable `PickupSegment` objects for the AGV components.

        Args:
            orders (list): A list of Order objects to be fulfilled.
            available_agvs (list): A list of currently idle AGV components.

        Returns:
            list[Task]: A list of newly created Task objects with optimal routes.
        """
        if len(orders) == 0 or len(available_agvs) == 0:
            return []

        # 1. Identify Points of Interest (POI)
        # -----------------------------------
        # Find the packing node closest to the center of the pickups, penalizing long queues
        packing_nodes = self.warehouse.packing_station_node_ids
        
        # Unique pickup locations
        pickup_nodes = list(set(order.item.node_id for order in orders))
        
        if pickup_nodes:
            import networkx as nx
            G_temp = self.warehouse.routing_graph._graph
            QUEUE_PENALTY = 1000.0 # High penalty ensures empty servers are chosen
            
            def score_packing_node(p_node_id):
                dist = nx.shortest_path_length(G_temp, pickup_nodes[0], p_node_id, weight='weight')
                q_length = 0
                if p_node_id in self.packing_queues_map:
                    q_length = len(self.packing_queues_map[p_node_id])
                return dist + (q_length * QUEUE_PENALTY)
                
            # Select packing node optimizing distance and queue length
            packing_node = min(packing_nodes, key=score_packing_node)
        else:
            packing_node = packing_nodes[0]
        
        # AGV start locations
        agv_start_nodes = {agv.agv_id: agv.current_node for agv in available_agvs}
        
        # Combine all POIs
        all_pois = list(set([packing_node] + pickup_nodes + list(agv_start_nodes.values())))
        poi_to_idx = {node_id: i for i, node_id in enumerate(all_pois)}
        n_pois = len(all_pois)
        #print(f"Number of POIs: {n_pois}")

        # 2. Build Distance Matrix (Pre-calculate shortest paths)
        # -------------------------------------------------------
        import networkx as nx
        G = self.warehouse.routing_graph._graph
        dist_matrix = {}
        path_matrix = {}
        
        for u in all_pois:
            for v in all_pois:
                if u == v:
                    dist_matrix[u, v] = 0
                    path_matrix[u, v] = [u]
                else:
                    path = nx.astar_path(G, u, v, weight='weight')
                    dist_matrix[u, v] = nx.path_weight(G, path, weight='weight')
                    path_matrix[u, v] = path

        # 3. Formulate VRP in Gurobi
        # --------------------------
        model = gp.Model("POI_VRP")
        model.Params.OutputFlag = 0

        V = [agv.agv_id for agv in available_agvs]
        O = [order.order_id for order in orders]
        agv_by_id = {agv.agv_id: agv for agv in available_agvs}
        
        # Decision Variables
        # x[i, j, v] = 1 if AGV v travels from POI i to POI j
        # y[o, v] = 1 if Order o is assigned to AGV v
        x = model.addVars(all_pois, all_pois, V, vtype=GRB.BINARY, name="x")
        y = model.addVars(O, V, vtype=GRB.BINARY, name="y")
        
        # Load and sequence variables (for MTZ subtour elimination)
        q = model.addVars(all_pois, V, lb=0, ub=MAX_PAYLOAD, name="q")
        u = model.addVars(all_pois, V, lb=0, ub=n_pois, name="u")

        # Linearization of quadratic objective (q * x)
        z = model.addVars(all_pois, all_pois, V, lb=0, name="z")

        # Objective: Minimize total energy consumption
        model.setObjective(
            gp.quicksum(
                dist_matrix[i, j] * (E_BASE * x[i, j, v] + ALPHA * z[i, j, v])
                for i in all_pois for j in all_pois for v in V if i != j
            ) - 1e6 * gp.quicksum(y[o, v] for o in O for v in V),
            GRB.MINIMIZE
        )

        # Constraints
        # -----------
        
        # Linearization constraints for z[i, j, v] = q[i, v] * x[i, j, v]
        for i in all_pois:
            for j in all_pois:
                for v in V:
                    if i != j:
                        model.addConstr(z[i, j, v] <= MAX_PAYLOAD * x[i, j, v])
                        model.addConstr(z[i, j, v] <= q[i, v])
                        model.addConstr(z[i, j, v] >= q[i, v] - MAX_PAYLOAD * (1 - x[i, j, v]))
        
        # Each order assigned to at most one AGV
        model.addConstrs((gp.quicksum(y[o, v] for v in V) <= 1 for o in O), name="order_assignment")

        # Innovation constraint: If False, restrict to max 1 order per AGV
        if not INNOVATION_ENABLED:
            model.addConstrs((gp.quicksum(y[o, v] for o in O) <= 1 for v in V), name="max_one_order")

        # Capacity constraints (Payload and Volume)
        model.addConstrs((gp.quicksum(orders[O.index(o)].item.weight * y[o, v] for o in O) <= MAX_PAYLOAD for v in V), name="max_payload")
        model.addConstrs((gp.quicksum(orders[O.index(o)].item.volume * y[o, v] for o in O) <= MAX_VOLUME for v in V), name="max_volume")

        # Simplified VRP Constraints (Standard VRP)
        for v in V:
            start_node = agv_start_nodes[v]
            is_used = model.addVar(vtype=GRB.BINARY, name=f"is_used_{v}")
            model.addConstr(is_used <= gp.quicksum(y[o, v] for o in O))
            model.addConstr(is_used >= gp.quicksum(y[o, v] for o in O) / 1000)

            # 1. Leave start node if used
            model.addConstr(gp.quicksum(x[start_node, j, v] for j in all_pois if j != start_node) == is_used)
            
            # 2. Arrive at packing node if used
            model.addConstr(gp.quicksum(x[i, packing_node, v] for i in all_pois if i != packing_node) == is_used)
            
            # 3. Intermediate nodes flow
            for p in all_pois:
                if p != start_node and p != packing_node:
                    inbound = gp.quicksum(x[i, p, v] for i in all_pois if i != p)
                    outbound = gp.quicksum(x[p, j, v] for j in all_pois if j != p)
                    model.addConstr(inbound == outbound)
                    
                    # Must visit node if order assigned there
                    orders_at_p = [o for o in O if orders[O.index(o)].item.node_id == p]
                    if orders_at_p:
                        v_p = model.addVar(vtype=GRB.BINARY, name=f"visit_{p}_{v}")
                        model.addConstr(inbound >= v_p)
                        for o in orders_at_p:
                            model.addConstr(v_p >= y[o, v])

            # 4. Capacity & MTZ for Subtour Elimination
            model.addConstr(q[start_node, v] == 0)
            for i in all_pois:
                for j in all_pois:
                    if i != j and j != start_node:
                        # Weight accumulation
                        orders_at_j = [o for o in O if orders[O.index(o)].item.node_id == j]
                        weight_at_j = gp.quicksum(orders[O.index(o)].item.weight * y[o, v] for o in orders_at_j) if orders_at_j else 0
                        model.addConstr(q[j, v] >= q[i, v] + weight_at_j - 1000 * (1 - x[i, j, v]))
                        # MTZ
                        model.addConstr(u[j, v] >= u[i, v] + 1 - n_pois * (1 - x[i, j, v]))

            model.addConstr(gp.quicksum(orders[O.index(o)].item.weight * y[o, v] for o in O) <= MAX_PAYLOAD)

        #print(f"Gurobi model - Vars: {model.NumVars}, Constrs: {model.NumConstrs}")
        model.optimize()
        
        if model.status != GRB.OPTIMAL:
            return []

        # 4. Reconstruct Tasks
        # --------------------
        from src.entities.task import Task, PickupSegment
        tasks = []
        
        for v in V:
            assigned_orders = [orders[O.index(o)] for o in O if y[o, v].X > 0.5]
            if not assigned_orders:
                continue
                
            # Trace POI path
            current_poi = agv_start_nodes[v]
            poi_path = [current_poi]
            while current_poi != packing_node:
                next_poi = next(j for j in all_pois if j != current_poi and x[current_poi, j, v].X > 0.5)
                poi_path.append(next_poi)
                current_poi = next_poi
                
            # Build full grid path and PickupSegments
            full_grid_path = []
            pickups = []
            
            for k in range(len(poi_path) - 1):
                segment_path = path_matrix[poi_path[k], poi_path[k+1]]
                
                # If destination POI is a pickup location
                target_node = poi_path[k+1]
                items_here = [o.item for o in assigned_orders if o.item.node_id == target_node]
                
                if items_here and target_node != packing_node:
                    # Everything up to target_node is the route for this segment
                    pickups.append(PickupSegment(
                        route=segment_path if not full_grid_path else segment_path,
                        items=items_here,
                        pick_time=(PICK_TIME_PER_ITEM * len(items_here)) / 60.0 # config value -> minutes
                    ))
                
                if k == 0:
                    full_grid_path.extend(segment_path)
                else:
                    full_grid_path.extend(segment_path[1:])
                    
            # Extract dropoff route (from last pickup to packing)
            if len(poi_path) >= 2:
                last_pickup_node = poi_path[-2]
                try:
                    split_idx = full_grid_path.index(last_pickup_node)
                    dropoff_route = full_grid_path[split_idx:]
                except ValueError:
                    dropoff_route = path_matrix[last_pickup_node, packing_node]
            else:
                dropoff_route = [packing_node]

            task = Task(
                task_id=self._generate_task_id(),
                orders=assigned_orders,
                pickups=pickups,
                dropoff_route=dropoff_route,
                route=full_grid_path,
                agv=agv_by_id[v],
                creation_time=self.env.now()
            )
            tasks.append(task)
            
        return tasks
