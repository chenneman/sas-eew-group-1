"""
Standalone test script for verifying AGV behavior.
Runs entirely isolated using mock Server and Charger components.
"""

import sys
import os
import salabim as sim

# Ensure the src directory is accessible
#sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.agv import AGV, AGVStatus
from src.models.task import Task, PickupSegment
from src.models.item import Item
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
    def setup(self, available_agvs: sim.Queue, routing_graph: RoutingGraph) -> None:
        self.available_agvs = available_agvs
        self.routing_graph = routing_graph
        self.task_count = 0

    def process(self):
        while True:
            self.hold(10)

            if len(self.available_agvs) > 0:
                agv = self.available_agvs.pop()
                self.task_count += 1

                # Create dummy items for multi-stop picking
                item1 = Item(sku=1, name="Chair", weight=15.0, length=1, width=1, height=1, volume=1, url="")
                item2 = Item(sku=2, name="Table", weight=20.0, length=1, width=1, height=1, volume=1, url="")

                # Route to first shelf
                route1 = self.routing_graph.get_shortest_path(agv.current_node, 2)
                seg1 = PickupSegment(route=route1, items=[item1], pick_time=5.0)

                # Route from first shelf to second shelf
                route2 = self.routing_graph.get_shortest_path(2, 5)
                seg2 = PickupSegment(route=route2, items=[item2], pick_time=4.0)

                # Route from final shelf to packing
                dropoff_route = self.routing_graph.get_shortest_path(5, 3)

                agv.current_task = Task(
                    task_id=self.task_count,
                    pickups=[seg1, seg2],
                    dropoff_route=dropoff_route
                )

                # Artificially drain battery to force charging test every other task
                if self.task_count % 2 == 0:
                    print(f"\n[Mock Dispatcher] Artificially draining AGV {agv.agv_id} battery to test charging sequence!\n")
                    agv.soc = agv.soc_threshold + 5.0  # Drop close to threshold so task drain pushes it under

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
        Node(4, (1 * pixel_scale, 10 * pixel_scale), NodeType.CHARGING),
        Node(5, (18 * pixel_scale, 5 * pixel_scale), NodeType.SHELF)
    ]

    for node in nodes_data:
        routing_graph.add_node(node)
        # Add animation elements using the node data
        sim.AnimateCircle(radius=5, x=node.coords[0], y=node.coords[1], fillcolor="white")
        sim.AnimateText(text=f"N{node.id} ({node.type.name})", 
                        x=node.coords[0] + 10, y=node.coords[1] + 10,
                        textcolor="white")

    # Define edges using domain model method (which calculates distances)
    edges = [(1, 2), (2, 5), (5, 3), (3, 1), (1, 4), (4, 2)]
    for u, v in edges:
        routing_graph.add_edge(u, v)

    server_q = sim.Queue("ServerQueue")
    charger_q = sim.Queue("ChargerQueue")
    available_agvs_q = sim.Queue("AvailableAGVs")

    server = MockServer(queue=server_q)
    charger = MockCharger(queue=charger_q)

    # Pass the RoutingGraph instance to the AGV and ControlSystem
    agv1 = AGV(agv_id=1, routing_graph=routing_graph, server_queue=server_q, charger_queue=charger_q, available_agvs=available_agvs_q)

    dispatcher = MockControlSystem(available_agvs=available_agvs_q, routing_graph=routing_graph)

    env.speed(40)
    env.run(1000)

if __name__ == "__main__":
    run_simulation()