"""
Standalone test script for verifying AGV behavior.
Runs entirely isolated using mock Server and Charger components.
"""

import sys
import os
import math
import networkx as nx
import salabim as sim

# Ensure the src directory is accessible
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.agv import AGV, AGVStatus
from src.models.task import Task
from src.models.graph import NodeType, Node, RoutingGraph


# --- Mock Components ---

class MockServer(sim.Component):
    def setup(self, queue: sim.Queue) -> None:
        self.queue = queue

    def process(self):
        while True:
            if len(self.queue) == 0:
                self.hold(1)
                continue
            
            agv = self.queue.pop()
            self.hold(8)
            agv.activate()


class MockCharger(sim.Component):
    def setup(self, queue: sim.Queue) -> None:
        self.queue = queue

    def process(self):
        while True:
            if len(self.queue) == 0:
                self.hold(1)
                continue

            agv = self.queue.pop()
            self.hold(15)
            agv.soc = agv.max_battery
            agv.activate()


class MockControlSystem(sim.Component):
    def setup(self, agvs: list, routing_graph: RoutingGraph) -> None:
        self.agvs = agvs
        self.routing_graph = routing_graph
        self.task_count = 0

    def process(self):
        while True:
            self.hold(10)

            idle_agvs = [agv for agv in self.agvs if agv.status == AGVStatus.IDLE]
            if idle_agvs:
                agv = idle_agvs[0]
                self.task_count += 1

                pickup_route = self.routing_graph.get_shortest_path(agv.current_node, 2)
                dropoff_route = self.routing_graph.get_shortest_path(2, 3)

                agv.current_task = Task(
                    task_id=self.task_count,
                    item_weight=10.0,
                    pick_time=5.0,
                    pickup_route=pickup_route,
                    dropoff_route=dropoff_route
                )

                # Artificially drain battery to force charging test every other task
                if self.task_count % 2 == 0:
                    agv.soc = 50.0

                agv.activate()


# --- Execution ---

def run_simulation() -> None:
    env = sim.Environment(trace=False)

    env.animate(True)  # Set to False if running in headless environment
    env.modelname("Isolated AGV Test")
    env.background_color("20%gray")

    pixel_scale = 30

    routing_graph = RoutingGraph()

    # Define Nodes using the domain model
    nodes_data = [
        Node(1, (1 * pixel_scale, 1 * pixel_scale), NodeType.IDLE),
        Node(2, (10 * pixel_scale, 10 * pixel_scale), NodeType.SHELF),
        Node(3, (10 * pixel_scale, 1 * pixel_scale), NodeType.PACKING),
        Node(4, (1 * pixel_scale, 10 * pixel_scale), NodeType.CHARGING)
    ]

    for node in nodes_data:
        routing_graph.add_node(node)
        # Add animation elements using the node data
        sim.AnimateCircle(radius=5, x=node.coords[0], y=node.coords[1], fillcolor="white")
        sim.AnimateText(text=f"N{node.id} ({node.type.name})", 
                        x=node.coords[0] + 10, y=node.coords[1] + 10,
                        textcolor="white")

    # Define edges using domain model method (which calculates distances)
    edges = [(1, 2), (2, 3), (3, 1), (1, 4), (4, 2)]
    for u, v in edges:
        routing_graph.add_edge(u, v)

    server_q = sim.Queue("ServerQueue")
    charger_q = sim.Queue("ChargerQueue")

    server = MockServer(queue=server_q)
    charger = MockCharger(queue=charger_q)

    # Pass the RoutingGraph instance to the AGV and ControlSystem
    agv1 = AGV(agv_id=1, routing_graph=routing_graph, server_queue=server_q, charger_queue=charger_q)

    dispatcher = MockControlSystem(agvs=[agv1], routing_graph=routing_graph)

    env.speed(20)
    env.run(1000)

if __name__ == "__main__":
    run_simulation()