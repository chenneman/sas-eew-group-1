"""
Central control system for the warehouse simulation.
Manages the order queue, dispatches idle AGVs, and uses a Gurobi optimization model
to route AGVs to pick up items efficiently.
"""

from typing import TYPE_CHECKING

import salabim as sim
import gurobipy as gp
from gurobipy import GRB
import networkx as nx

from src.components.agv import AGVStatus
from src.entities.task import Task, PickupSegment

from src.config import (BATCH_SIZE, MAX_WAIT_TIME, MAX_VOLUME, MAX_PAYLOAD,
                        E_BASE, ALPHA, INNOVATION_ENABLED, PICK_TIME_PER_ITEM)

import logging

if TYPE_CHECKING:
    from src.environment.warehouse import Warehouse
    from src.entities.order import Order
    from src.components.agv import AGV

logger = logging.getLogger(__name__)

class ControlSystem(sim.Component):
    """
    The brain of the AGV fleet. Pools incoming orders into batches and uses a Mixed-Integer
    Programming (MIP) model via Gurobi to assign orders and calculate optimal routing paths.
    """
    def setup(
        self,
        warehouse: 'Warehouse',
        order_queue: list['Order'],
        available_agvs: sim.Queue,
        batch_size: int = BATCH_SIZE,
        max_wait_time: float = MAX_WAIT_TIME,
        packing_queues_map: dict[int, sim.Queue] | None = None
    ) -> None:
        """
        Initializes the ControlSystem component.

        Args:
            warehouse: The Warehouse environment component containing the layout graph.
            order_queue: The list containing pending Orders.
            available_agvs: The queue containing idle AGVs ready for dispatch.
            batch_size: The number of orders to pool before triggering a routing run.
            max_wait_time: The maximum time (in sim minutes) to wait for a full batch before triggering.
            packing_queues_map: Mapping of packing node IDs to their respective Salabim Queues.
        """
        self.warehouse = warehouse
        self.order_queue = order_queue
        self.available_agvs = available_agvs
        self.batch_size = batch_size
        self.max_wait_time = max_wait_time
        self.packing_queues_map = packing_queues_map or {}
        self.agvs: sim.Queue = available_agvs
        self.last_batch_time: float = 0.0
        self.task_counter: int = 0

    def _generate_task_id(self) -> int:
        """Generates a unique sequential task ID."""
        self.task_counter += 1
        return self.task_counter

    def process(self) -> None:
        """Main event-driven lifecycle loop of the control system."""
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
            if len(self.order_queue) < self.batch_size:
                time_since_last = self.env.now() - self.last_batch_time
                
                # Use a small epsilon to avoid floating point precision loops
                if time_since_last < self.max_wait_time - 1e-7:
                    wait_remaining = self.max_wait_time - time_since_last
                    logger.debug(f"[{self.env.now():.2f}] [ControlSystem] Waiting for more orders. {len(self.order_queue)}/{self.batch_size} in queue. Timeout in {wait_remaining:.3f} min.")
                    self.hold(wait_remaining)
                    continue
                else:
                    logger.info(f"[{self.env.now():.2f}] [ControlSystem] Batch timeout reached ({self.max_wait_time} min). Processing {len(self.order_queue)} orders.")

            # 4. Execute Routing Logic
            num_available = len(available_agvs)
            max_batch_to_check = num_available * self.batch_size
            batch_orders = list(self.order_queue)[:max_batch_to_check]

            logger.info(f"[{self.env.now():.2f}] [ControlSystem] Triggering routing for {len(batch_orders)} orders with {num_available} AGVs.")
            tasks = self.routing_algorithm(
                orders=batch_orders,
                available_agvs=available_agvs
            )

            # 5. Assign tasks
            if not tasks:
                logger.warning("[ControlSystem] Routing algorithm returned no tasks.")
            
            for task in tasks:
                agv = task.agv
                logger.info(f"[ControlSystem] Assigned Task {task.task_id} to AGV {agv.agv_id} ({len(task.orders)} orders)")
                if agv in self.available_agvs:
                    agv.leave(self.available_agvs)
                
                agv.current_task = task
                agv.route = task.route
                agv.orders = task.orders
                agv.status = AGVStatus.MOVING
                for order in task.orders:
                    order.status = "ASSIGNED"
                    order.assignment_min = self.env.now()
                    order.event_log.append((self.env.now(), f"Assigned to AGV {agv.agv_id} as Task {task.task_id}")) #additional for verification
                    self.order_queue.remove(order)
                agv.activate()

            self.last_batch_time = self.env.now()
            self.hold(0)

    def routing_algorithm(self, orders: list['Order'], available_agvs: list['AGV']) -> list[Task]:
        """
        Executes a Point-of-Interest (POI) based Vehicle Routing Problem (VRP) using Gurobi.
        """
        if not orders or not available_agvs:
            return []

        # 1. Identify POIs
        packing_node, pickup_nodes, agv_start_nodes, all_pois = self._identify_pois(orders, available_agvs)

        # 2. Build Distance Matrix
        dist_matrix, path_matrix = self._build_distance_matrix(all_pois)

        # 3. Formulate and Solve VRP
        solution = self._optimize_routes(
            orders, available_agvs, all_pois, agv_start_nodes, packing_node, dist_matrix
        )
        
        if not solution:
            return []

        # 4. Reconstruct Tasks
        return self._reconstruct_tasks(solution, path_matrix, packing_node, available_agvs)

    def _identify_pois(self, orders: list['Order'], available_agvs: list['AGV']) -> tuple[int, list[int], dict[int, int], list[int]]:
        """Identifies unique locations of interest for the optimization model."""
        packing_nodes = self.warehouse.packing_station_node_ids
        pickup_nodes = list(set(order.item.node_id for order in orders))
        
        G = self.warehouse.routing_graph._graph
        QUEUE_PENALTY = 1000.0
        
        def score_packing_node(p_node_id: int) -> float:
            # Score based on distance to first pickup and current queue length
            dist = nx.shortest_path_length(G, pickup_nodes[0], p_node_id, weight='weight') if pickup_nodes else 0
            q_length = len(self.packing_queues_map[p_node_id]) if p_node_id in self.packing_queues_map else 0
            return dist + (q_length * QUEUE_PENALTY)
            
        packing_node = min(packing_nodes, key=score_packing_node)
        agv_start_nodes = {agv.agv_id: agv.current_node for agv in available_agvs}
        all_pois = list(set([packing_node] + pickup_nodes + list(agv_start_nodes.values())))
        
        return packing_node, pickup_nodes, agv_start_nodes, all_pois

    def _build_distance_matrix(self, pois: list[int]) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], list[int]]]:
        """Calculates shortest paths and distances between all pairs of POIs."""
        G = self.warehouse.routing_graph._graph
        dist_matrix = {}
        path_matrix = {}
        
        for u in pois:
            for v in pois:
                if u == v:
                    dist_matrix[u, v] = 0.0
                    path_matrix[u, v] = [u]
                else:
                    path = nx.astar_path(G, u, v, weight='weight')
                    dist_matrix[u, v] = float(nx.path_weight(G, path, weight='weight'))
                    path_matrix[u, v] = path
                    
        return dist_matrix, path_matrix

    def _optimize_routes(
        self, 
        orders: list['Order'], 
        available_agvs: list['AGV'], 
        all_pois: list[int], 
        agv_start_nodes: dict[int, int], 
        packing_node: int, 
        dist_matrix: dict[tuple[int, int], float]
    ) -> dict | None:
        """Formulates and solves the MIP model using Gurobi."""
        model = gp.Model("POI_VRP")
        model.Params.OutputFlag = 0
        model.Params.TimeLimit = 15.0  # Seconds
        model.Params.MIPGap = 0.05    # 5% optimality gap for speed

        V = [agv.agv_id for agv in available_agvs]
        O = [order.order_id for order in orders]
        n_pois = len(all_pois)
        
        # Decision Variables
        x = model.addVars(all_pois, all_pois, V, vtype=GRB.BINARY, name="x")
        y = model.addVars(O, V, vtype=GRB.BINARY, name="y")
        q = model.addVars(all_pois, V, lb=0, ub=MAX_PAYLOAD, name="q")
        u = model.addVars(all_pois, V, lb=0, ub=n_pois, name="u")
        z = model.addVars(all_pois, all_pois, V, lb=0, name="z")

        # Objective: Minimize energy consumption (Distance * (Base + Alpha * Load))
        # Penalty for unfulfilled orders (1e4 is large enough to prioritize fulfillment over distance)
        model.setObjective(
            gp.quicksum(
                dist_matrix[i, j] * (E_BASE * x[i, j, v] + ALPHA * z[i, j, v])
                for i in all_pois for j in all_pois for v in V if i != j
            ) - 1e4 * gp.quicksum(y[o, v] for o in O for v in V),
            GRB.MINIMIZE
        )

        # Constraints
        # 1. Linearization for z = q * x
        for i in all_pois:
            for j in all_pois:
                for v in V:
                    if i != j:
                        model.addConstr(z[i, j, v] <= MAX_PAYLOAD * x[i, j, v])
                        model.addConstr(z[i, j, v] <= q[i, v])
                        model.addConstr(z[i, j, v] >= q[i, v] - MAX_PAYLOAD * (1 - x[i, j, v]))
        
        # 2. Assignment & Capacity
        model.addConstrs((gp.quicksum(y[o, v] for v in V) <= 1 for o in O))
        if not INNOVATION_ENABLED:
            model.addConstrs((gp.quicksum(y[o, v] for o in O) <= 1 for v in V))

        model.addConstrs((gp.quicksum(orders[O.index(o)].item.weight * y[o, v] for o in O) <= MAX_PAYLOAD for v in V))
        model.addConstrs((gp.quicksum(orders[O.index(o)].item.volume * y[o, v] for o in O) <= MAX_VOLUME for v in V))

        # 3. Routing & Flow
        for v in V:
            start_node = agv_start_nodes[v]
            is_used = model.addVar(vtype=GRB.BINARY, name=f"is_used_{v}")
            model.addConstr(is_used <= gp.quicksum(y[o, v] for o in O))
            model.addConstr(is_used >= gp.quicksum(y[o, v] for o in O) / max(1, len(O)))

            model.addConstr(gp.quicksum(x[start_node, j, v] for j in all_pois if j != start_node) == is_used)
            model.addConstr(gp.quicksum(x[i, packing_node, v] for i in all_pois if i != packing_node) == is_used)
            
            for p in all_pois:
                if p != start_node and p != packing_node:
                    inbound = gp.quicksum(x[i, p, v] for i in all_pois if i != p)
                    outbound = gp.quicksum(x[p, j, v] for j in all_pois if j != p)
                    model.addConstr(inbound == outbound)
                    
                    orders_at_p = [o for o in O if orders[O.index(o)].item.node_id == p]
                    if orders_at_p:
                        v_p = model.addVar(vtype=GRB.BINARY, name=f"visit_{p}_{v}")
                        model.addConstr(inbound >= v_p)
                        for o in orders_at_p:
                            model.addConstr(v_p >= y[o, v])

            # 4. Subtour Elimination (MTZ)
            model.addConstr(q[start_node, v] == 0)
            for i in all_pois:
                for j in all_pois:
                    if i != j and j != start_node:
                        orders_at_j = [o for o in O if orders[O.index(o)].item.node_id == j]
                        weight_at_j = gp.quicksum(orders[O.index(o)].item.weight * y[o, v] for o in orders_at_j) if orders_at_j else 0
                        model.addConstr(q[j, v] >= q[i, v] + weight_at_j - MAX_PAYLOAD * (1 - x[i, j, v]))
                        model.addConstr(u[j, v] >= u[i, v] + 1 - n_pois * (1 - x[i, j, v]))

        model.optimize()
        
        if model.status != GRB.OPTIMAL:
            if model.status == GRB.TIME_LIMIT:
                logger.warning(f"[{self.env.now():.2f}] [ControlSystem] Gurobi hit time limit. Status: {model.status}")
                if model.SolCount > 0:
                    logger.info("Using best found sub-optimal solution.")
                else:
                    return None
            elif model.status == GRB.INFEASIBLE:
                logger.error(f"[{self.env.now():.2f}] [ControlSystem] Gurobi model is INFEASIBLE.")
                return None
            else:
                logger.warning(f"[{self.env.now():.2f}] [ControlSystem] Gurobi ended with status {model.status}")
                return None

        # Return relevant results for reconstruction
        return {
            'x': model.getAttr('X', x),
            'y': model.getAttr('X', y),
            'pois': all_pois,
            'agv_ids': V,
            'order_ids': O,
            'agv_start_nodes': agv_start_nodes
        }

    def _reconstruct_tasks(self, solution: dict, path_matrix: dict, packing_node: int, available_agvs: list['AGV']) -> list[Task]:
        """Converts the optimization solution into actionable Task objects."""
        tasks = []
        agv_by_id = {agv.agv_id: agv for agv in available_agvs}
        orders_by_id = {o.order_id: o for o in self.order_queue} # Note: using full queue for lookup
        
        x_vals = solution['x']
        y_vals = solution['y']
        all_pois = solution['pois']
        
        for v in solution['agv_ids']:
            assigned_orders = [orders_by_id[o] for o in solution['order_ids'] if y_vals[o, v] > 0.5]
            if not assigned_orders:
                continue
                
            # Trace POI path
            current_poi = solution['agv_start_nodes'][v]
            poi_path = [current_poi]
            
            # Safety break to prevent infinite loops during reconstruction
            max_steps = len(all_pois) + 1
            steps = 0
            
            while current_poi != packing_node and steps < max_steps:
                steps += 1
                try:
                    next_poi = next(j for j in all_pois if j != current_poi and x_vals[current_poi, j, v] > 0.5)
                    poi_path.append(next_poi)
                    current_poi = next_poi
                except StopIteration:
                    logger.error(f"[ControlSystem] Failed to find next POI for AGV {v} at node {current_poi}")
                    break
            
            if steps >= max_steps:
                logger.error(f"[ControlSystem] Path reconstruction exceeded max steps for AGV {v}. Subtour detected?")
                continue
                
            # Build full grid path and PickupSegments
            full_grid_path: list[int] = []
            pickups: list[PickupSegment] = []
            
            for k in range(len(poi_path) - 1):
                segment_path = path_matrix[poi_path[k], poi_path[k+1]]
                target_node = poi_path[k+1]
                items_here = [o.item for o in assigned_orders if o.item.node_id == target_node]
                
                if items_here and target_node != packing_node:
                    pickups.append(PickupSegment(
                        route=segment_path,
                        items=items_here,
                        pick_time=(PICK_TIME_PER_ITEM * len(items_here)) / 60.0
                    ))
                
                if k == 0:
                    full_grid_path.extend(segment_path)
                else:
                    full_grid_path.extend(segment_path[1:])
                    
            # Extract dropoff route
            if len(poi_path) >= 2:
                last_pickup_node = poi_path[-2]
                try:
                    split_idx = full_grid_path.index(last_pickup_node)
                    dropoff_route = full_grid_path[split_idx:]
                except ValueError:
                    dropoff_route = path_matrix[last_pickup_node, packing_node]
            else:
                dropoff_route = [packing_node]

            tasks.append(Task(
                task_id=self._generate_task_id(),
                orders=assigned_orders,
                pickups=pickups,
                dropoff_route=dropoff_route,
                route=full_grid_path,
                agv=agv_by_id[v],
                creation_time=self.env.now()
            ))
            
        return tasks

