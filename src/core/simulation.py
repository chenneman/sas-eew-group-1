"""
Core Simulation Engine.
Orchestrates the setup and execution of the Salabim environment and all components.
"""

import salabim as sim

# Environment
from src.environment.warehouse import Warehouse
from src.environment.service_time_generator import ServiceTimeGenerator

# Components
from src.components.control_system import ControlSystem
from src.components.agv import AGV
from src.components.server import Server
from src.components.charger import Charger
from src.components.order_generator import OrderGenerator

# Entities
from src.entities.item import load_items

# Config
from src.config import (
    N_AGV,
    N_SERVERS,
    N_CHARGERS,
    CHARGE_RATE,
    MAX_BATTERY
)


from src.core.metrics import SimulationMetrics

class SimulationEngine:
    """
    Wraps the Salabim environment and initializes all required simulation entities.
    """

    def __init__(self, trace: bool = False, animate: bool = False):
        self.env = sim.Environment(trace=trace)
        self.animate = animate
        self.metrics = SimulationMetrics()

        if self.animate:
            self.env.animation_parameters(animate=True, speed=10, width=1200, height=800)
            self.env.background_color("black")

        self._build_world()
        self._instantiate_queues()
        self._boot_components()
        
        if self.animate:
            self._build_ui()

    def _build_world(self):
        """Initializes the static warehouse layout and math engines."""
        # Load items (using default paths configured in utils)
        self.items = load_items()

        # Build the warehouse map (pure layout, no item injection)
        self.warehouse = Warehouse()

        # Sequentially map items to physical shelf nodes (1-to-1)
        shelf_nodes = self.warehouse.shelf_node_ids
        for item, shelf_id in zip(self.items, shelf_nodes):
            item.node_id = shelf_id

        # Initialize math engine
        self.service_time_generator = ServiceTimeGenerator()

    def _build_ui(self):
        """Creates the on-screen UI overlay for real-time metrics."""
        # Background for the metrics box (Top Right)
        sim.AnimateRectangle(
            spec=(950, 650, 1180, 780),
            fillcolor="black",
            linecolor="white",
            linewidth=2,
            arg="UI"
        )
        
        # Simulation Time
        sim.AnimateText(
            text=lambda t: f"Time: {self.env.now():.1f} min",
            x=970, y=750,
            textcolor="white", fontsize=18
        )
        
        # Orders Completed
        def get_completed_count(t):
            count = sum(len(server.processed_orders) for server in self.servers)
            return f"Completed: {count}"
            
        sim.AnimateText(
            text=get_completed_count,
            x=970, y=720,
            textcolor="cyan", fontsize=16
        )
        
        # Pending Orders
        sim.AnimateText(
            text=lambda t: f"Pending: {len(self.order_queue)}",
            x=970, y=690,
            textcolor="yellow", fontsize=16
        )
        
        # Active AGVs
        def get_active_agvs(t):
            active = sum(1 for agv in self.agvs if agv.status != "IDLE")
            return f"Active AGVs: {active}/{len(self.agvs)}"
            
        sim.AnimateText(
            text=get_active_agvs,
            x=970, y=660,
            textcolor="white", fontsize=14
        )

    def _instantiate_queues(self):
        """Creates the central communication queues and component mappings."""
        self.order_queue = [] # Standard list because Orders are passive dataclasses
        self.available_agvs = sim.Queue("available_agvs")
        self.server_queue = sim.Queue("server_queue")
        self.charger_queue = sim.Queue("charger_queue")
        
        # Mappings for event-driven wakeups
        self.queue_to_component = {}

    def _boot_components(self):
        """Spawns all active sim.Components."""
        
        # 1. Spawn Control System first so others can reference it
        self.control_system = ControlSystem(
            warehouse=self.warehouse,
            order_queue=self.order_queue,
            available_agvs=self.available_agvs
        )
        self.queue_to_component[self.available_agvs] = self.control_system
        
        # 2. Spawn Order Generator
        self.order_generator = OrderGenerator(
            order_queue=self.order_queue,
            items=self.items,
            control_system=self.control_system
        )

        # 3. Spawn Servers (Packing Stations)
        self.servers = []
        for i in range(1, N_SERVERS + 1):
            server = Server(
                server_id=i,
                queue=self.server_queue,
                service_time_generator=self.service_time_generator,
            )
            self.servers.append(server)
        self.queue_to_component[self.server_queue] = self.servers # Mapping to fleet

        # 4. Spawn Chargers
        self.chargers = []
        for i in range(1, N_CHARGERS + 1):
            charger = Charger(
                charger_id=i,
                queue=self.charger_queue,
                charging_rate=CHARGE_RATE
            )
            self.chargers.append(charger)
        self.queue_to_component[self.charger_queue] = self.chargers # Mapping to fleet

        # 5. Spawn AGVs
        self.agvs = []
        for i in range(1, N_AGV + 1):
            agv = AGV(
                agv_id=i,
                routing_graph=self.warehouse.routing_graph,
                server_queue=self.server_queue,
                charger_queue=self.charger_queue,
                available_agvs=self.available_agvs,
                queue_to_component=self.queue_to_component
            )
            # For testing: start with low battery (5%) to trigger charging soon
            agv.battery = MAX_BATTERY * 0.05
            self.agvs.append(agv)

        self.control_system.agvs = self.agvs # Inject complete fleet reference

    def finalize_metrics(self):
        """Aggregates all component-level data into the central metrics object."""
        # 1. Aggregate Server data (Orders completed and fulfillment times)
        for server in self.servers:
            self.metrics.total_orders_completed += len(server.processed_orders)
            for order in server.processed_orders:
                fulfillment_time = order.completion_time - order.arrival_min
                self.metrics.order_fulfillment_times.append(fulfillment_time)
        
        # 2. Aggregate AGV data (Energy and task counts)
        for agv in self.agvs:
            self.metrics.energy_consumed_wh += agv.total_energy_consumed
            self.metrics.agv_metrics[agv.agv_id] = {
                "energy": agv.total_energy_consumed,
                "tasks": agv.tasks_completed
            }

    def run(self, till: float):
        """Executes the simulation for the specified duration."""
        self.env.run(till=till)
        self.finalize_metrics()

