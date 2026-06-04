"""
Standalone test script for verifying AGV behavior, specifically focusing on the charging lifecycle.
Runs isolated using mock Server and Charger components.
"""

import salabim as sim

from src.components.agv import AGV, AGVStatus
from src.entities.task import Task, PickupSegment
from src.entities.item import Item
from src.environment.graph import NodeType, Node, RoutingGraph
from src.utils.animation import grid_to_pixel

from src.config import MAX_BATTERY, BATTERY_THRESHOLD, CHARGE_RATE

# --- Mock Components ---

class MockServer(sim.Component):
    """Simple mock server that processes AGVs from a queue."""
    def setup(self, queue: sim.Queue) -> None:
        self.queue = queue

    def process(self):
        while True:
            if len(self.queue) == 0:
                self.passivate()
                continue

            agv = self.queue.pop()
            print(f"[Mock Server] Unloading AGV {agv.agv_id}...")
            self.hold(5) # Unloading time
            agv.activate()


class MockCharger(sim.Component):
    """Simple mock charger that refills AGV battery."""
    def setup(self, queue: sim.Queue) -> None:
        self.queue = queue

    def process(self):
        while True:
            if len(self.queue) == 0:
                self.passivate()
                continue

            agv = self.queue.pop()
            print(f"[Mock Charger] Charging AGV {agv.agv_id}...")
            
            # Calculate time to full
            missing_charge = MAX_BATTERY - agv.battery
            charge_time = missing_charge / CHARGE_RATE
            
            self.hold(charge_time)
            agv.battery = MAX_BATTERY
            print(f"[Mock Charger] AGV {agv.agv_id} fully charged.")
            agv.activate()


class MockControlSystem(sim.Component):
    """Dispatches tasks and forces low-battery states for testing."""
    def setup(self, available_agvs: sim.Queue, routing_graph: RoutingGraph) -> None:
        self.available_agvs = available_agvs
        self.routing_graph = routing_graph
        self.task_count = 0

    def process(self):
        while True:
            if len(self.available_agvs) == 0:
                self.passivate()
                continue

            agv = self.available_agvs.pop()
            self.task_count += 1
            print(f"\n[Mock Dispatcher] Dispatching Task {self.task_count} to AGV {agv.agv_id}")

            # Create dummy items
            item1 = Item(sku=101, name="Widget", weight=5.0, length=1, width=1, height=1, volume=1, url="")
            
            # Simple route: Node 1 (IDLE) -> Node 2 (SHELF) -> Node 3 (PACKING)
            route_to_shelf = self.routing_graph.get_shortest_path(agv.current_node, 2)
            seg = PickupSegment(route=route_to_shelf, items=[item1], pick_time=2.0)
            
            dropoff_route = self.routing_graph.get_shortest_path(2, 3)

            agv.current_task = Task(
                task_id=self.task_count,
                pickups=[seg],
                dropoff_route=dropoff_route
            )

            # Force charging every 3rd task by draining battery significantly below threshold
            if self.task_count % 3 == 0:
                print(f"[Mock Dispatcher] !!! FORCING LOW BATTERY on AGV {agv.agv_id} !!!")
                agv.battery = BATTERY_THRESHOLD - 10.0
            
            agv.activate()
            self.hold(20) # Wait before next dispatch


# --- Execution ---

def run_simulation() -> None:
    env = sim.Environment(trace=False)
    env.animate(True)
    env.modelname("AGV Charging Lifecycle Test")
    env.background_color("black")

    # 1. Build Graph
    routing_graph = RoutingGraph()
    nodes = [
        Node(1, (2, 2), NodeType.IDLE),
        Node(2, (15, 15), NodeType.SHELF),
        Node(3, (25, 2), NodeType.PACKING),
        Node(4, (2, 15), NodeType.CHARGING),
    ]
    for n in nodes:
        routing_graph.add_node(n)
        px, py = grid_to_pixel(n.coords[0]), grid_to_pixel(n.coords[1])
        sim.AnimateCircle(radius=10, x=px, y=py, fillcolor="white", linecolor="gray")
        sim.AnimateText(text=f"{n.id}:{n.type.name}", x=px, y=py+20, textcolor="white")

    edges = [(1, 2), (2, 3), (3, 1), (1, 4), (4, 2)]
    for u, v in edges:
        routing_graph.add_edge(u, v)

    # 2. Queues
    server_q = sim.Queue("ServerQueue")
    charger_q = sim.Queue("ChargerQueue")
    available_agvs_q = sim.Queue("AvailableAGVs")

    # 3. Components
    server = MockServer(queue=server_q)
    charger = MockCharger(queue=charger_q)
    
    # AGV activation helper
    def on_enter_queue(arg):
        if isinstance(arg, sim.Queue):
            if arg == server_q and server.ispassive():
                server.activate()
            elif arg == charger_q and charger.ispassive():
                charger.activate()

    # Note: In a real scenario, use monkeypatch or use a custom Queue that activates the server.
    # For this test, manually ensure they wake up.
    
    agv = AGV(
        agv_id=1, 
        routing_graph=routing_graph, 
        server_queue=server_q, 
        charger_queue=charger_q, 
        available_agvs=available_agvs_q
    )

    dispatcher = MockControlSystem(
        available_agvs=available_agvs_q, 
        routing_graph=routing_graph
    )

    # Manual activation injection (simplified)
    original_enter = agv.enter
    def patched_enter(queue):
        original_enter(queue)
        if queue == server_q and server.ispassive(): server.activate()
        if queue == charger_q and charger.ispassive(): charger.activate()
        if queue == available_agvs_q and dispatcher.ispassive(): dispatcher.activate()
    agv.enter = patched_enter

    # 4. UI Overlay
    sim.AnimateText(text=lambda t: f"Time: {env.now():.1f} min", x=50, y=750, textcolor="white", fontsize=20)
    sim.AnimateText(text=lambda t: f"AGV Battery: {agv.battery:.1f}Wh ({agv.soc:.1f}%)", 
                    x=50, y=720, textcolor=lambda t: "red" if agv.battery < BATTERY_THRESHOLD else "green")

    print("\n--- Starting AGV Charging Test ---")
    env.speed(16)
    env.run(500)
    print("\n--- Test Finished ---")

if __name__ == "__main__":
    run_simulation()
