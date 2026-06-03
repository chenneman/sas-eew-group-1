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
    MAX_BATTERY,
    INITIAL_ANIM_SPEED,
    INITIAL_BATTERY_FACTOR,
    LOG_TRACE_TO_FILE
)

from src.utils.paths import LOGS_DIR

from src.core.metrics import SimulationMetrics

class SimulationEngine:
    """
    Wraps the Salabim environment and initializes all required simulation entities.
    """

    def __init__(self, trace: bool = False, animate: bool = False):
        self.env = sim.Environment(trace=trace)
        self.animate = animate
        self.metrics = SimulationMetrics()
        
        if LOG_TRACE_TO_FILE:
            self.env.trace(True)
            # Route salabim trace to file
            self._trace_file = open("logs/trace.log", "w")
            self.env.trace(out=self._trace_file)

        if self.animate:
            self.env.animation_parameters(animate=True, speed=INITIAL_ANIM_SPEED, width=1200, height=800)
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
        self.warehouse.build_queues(self.env)

        # Sequentially map items to physical pick nodes (1-to-1)
        pick_nodes = self.warehouse.pick_node_ids
        for item, pick_id in zip(self.items, pick_nodes):
            item.node_id = pick_id

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
        
        # Live Order Log Background (Right side)
        sim.AnimateRectangle(
            spec=(950, 50, 1180, 600),
            fillcolor="#111111",
            linecolor="gray",
            linewidth=1,
            arg="UI"
        )
        
        sim.AnimateText(
            text="Live Orders",
            x=960, y=575,
            textcolor="lightgreen", fontsize=14
        )
        
        # Function to render the last 25 lines of the order log
        def get_log_text(t):
            lines = self.live_order_log[-25:]
            return "\n".join(lines)
            
        sim.AnimateText(
            text=get_log_text,
            x=960, y=550,
            textcolor="lightgray", fontsize=10,
            text_anchor="nw"
        )

    def _instantiate_queues(self):
        """Creates the central communication queues and component mappings."""
        self.order_queue = [] # Standard list because Orders are passive dataclasses
        self.live_order_log = [] # List of strings for UI display
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
            available_agvs=self.available_agvs,
            packing_queues_map={q["node_id"]: q["queue"] for q in self.warehouse.packing_queues}
        )
        self.queue_to_component[self.available_agvs] = self.control_system
        
        # 2. Spawn Order Generator
        self.order_generator = OrderGenerator(
            order_queue=self.order_queue,
            items=self.items,
            control_system=self.control_system,
            live_order_log=self.live_order_log
        )

        # 3. Spawn Servers (Packing Stations)
        self.servers = []
        for q_info in self.warehouse.packing_queues:
            server = Server(
                server_id=q_info["id"],
                queue=q_info["queue"],
                service_time_generator=self.service_time_generator,
            )
            self.servers.append(server)
            self.queue_to_component[q_info["queue"]] = server

        # 4. Spawn Chargers
        self.chargers = []
        for q_info in self.warehouse.charger_queues:
            charger = Charger(
                charger_id=q_info["id"],
                queue=q_info["queue"],
                charging_rate=CHARGE_RATE
            )
            self.chargers.append(charger)
            self.queue_to_component[q_info["queue"]] = charger

        # 5. Spawn AGVs
        self.agvs = []
        for i in range(1, N_AGV + 1):
            agv = AGV(
                agv_id=i,
                routing_graph=self.warehouse.routing_graph,
                server_queue=self.server_queue, # Default shared queue for legacy, will be updated to specific
                charger_queue=self.charger_queue, # Default shared queue for legacy
                available_agvs=self.available_agvs,
                queue_to_component=self.queue_to_component,
                charger_queues_map={q["node_id"]: q["queue"] for q in self.warehouse.charger_queues},
                packing_queues_map={q["node_id"]: q["queue"] for q in self.warehouse.packing_queues}
            )
            # Apply battery factor from config
            agv.battery = MAX_BATTERY * INITIAL_BATTERY_FACTOR
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

