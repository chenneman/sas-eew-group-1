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
from src.components.agv import AGV, AGVStatus
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
    LOG_TRACE_TO_FILE,
    RANDOM_SEED,
    ANIMATE,
    SIM_START_HOUR,
    WARMUP_MIN
)

from src.utils.paths import LOGS_DIR

from src.core.metrics import SimulationMetrics

class WarmupManager(sim.Component):
    """Component that waits for the warmup period and then resets component metrics."""
    def setup(self, engine, warmup_time: float):
        self.engine = engine
        self.warmup_time = warmup_time

    def process(self):
        self.hold(self.warmup_time)
        print(f"\n--- Warmup Period ({self.warmup_time} min) Finished. Resetting Metrics... ---")
        
        # Manually reset relevant monitors for KPI tracking
        for agv in self.engine.agvs:
            agv.total_energy_consumed = 0.0
            agv.tasks_completed = 0
            agv.total_distance = 0.0
            agv.total_stops = 0
            agv.mode.reset()
            agv.soc_monitor.reset()
            
        for server in self.engine.servers:
            server.queue.length_of_stay.reset()

class SimulationEngine:
    """
    Wraps the Salabim environment and initializes all required simulation entities.
    Supports the context manager pattern for robust log file handling.
    """

    def __init__(self, animate: bool = None):
        self.animate = animate if animate is not None else ANIMATE
        self.metrics = SimulationMetrics()
        self._trace_file = None
        self.env = None

    def __enter__(self):
        """Initializes the simulation environment and logs."""
        if LOG_TRACE_TO_FILE:
            if not LOGS_DIR.exists():
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
            self._trace_file = open(LOGS_DIR / "trace.log", "w")
            self.env = sim.Environment(trace=self._trace_file, random_seed=RANDOM_SEED)
        else:
            self.env = sim.Environment(trace=False, random_seed=RANDOM_SEED)

        if self.animate:
            self.env.animation_parameters(animate=True, speed=INITIAL_ANIM_SPEED, width=1920, height=1080)
            self.env.background_color("black")

        self._build_world()
        self._instantiate_queues()
        self._boot_components()
        
        if self.animate:
            self._build_ui()
            
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures log files are properly closed."""
        if self._trace_file:
            self._trace_file.close()

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
        # Background for the metrics box (Top Right, expanded to fit all text)
        sim.AnimateRectangle(
            spec=(860, 620, 1140, 780),
            fillcolor="black",
            linecolor="white",
            linewidth=2,
            arg="UI"
        )
        
        # Real-world Clock (HH:MM)
        def get_clock_time(t):
            total_mins = self.env.now() + (SIM_START_HOUR * 60)
            hrs = int((total_mins // 60) % 24)
            mins = int(total_mins % 60)
            return f"{hrs:02d}:{mins:02d}"

        sim.AnimateText(
            text=get_clock_time,
            x=880, y=760,
            textcolor="lightgray", fontsize=14,
            text_anchor="nw"
        )

        # Simulation Time (Cumulative)
        sim.AnimateText(
            text=lambda t: f"Sim Time: {self.env.now():.1f} min",
            x=880, y=740,
            textcolor="white", fontsize=16,
            text_anchor="nw"
        )
        
        # Orders Completed
        def get_completed_count(t):
            count = sum(len(server.processed_orders) for server in self.servers)
            return f"Completed: {count}"
            
        sim.AnimateText(
            text=get_completed_count,
            x=880, y=710,
            textcolor="cyan", fontsize=16,
            text_anchor="nw"
        )
        
        # Pending Orders
        sim.AnimateText(
            text=lambda t: f"Pending: {len(self.order_queue)}",
            x=880, y=680,
            textcolor="yellow", fontsize=16,
            text_anchor="nw"
        )
        
        # In-Progress Orders (Assigned but not yet completed)
        def get_in_progress(t):
            total_gen = self.order_generator.orders_generated
            fulfilled = sum(len(server.processed_orders) for server in self.servers)
            pending = len(self.order_queue)
            return f"In-Progress: {total_gen - fulfilled - pending}"
            
        sim.AnimateText(
            text=get_in_progress,
            x=880, y=650,
            textcolor="orange", fontsize=15,
            text_anchor="nw"
        )
        
        # Active AGVs
        def get_active_agvs(t):
            active = sum(1 for agv in self.agvs if agv.status != AGVStatus.IDLE)
            return f"Active AGVs: {active}/{len(self.agvs)}"
            
        sim.AnimateText(
            text=get_active_agvs,
            x=880, y=625,
            textcolor="white", fontsize=14,
            text_anchor="nw"
        )
        
        # Live Order Log Background (Right side)
        sim.AnimateRectangle(
            spec=(860, 50, 1140, 600),
            fillcolor="#111111",
            linecolor="gray",
            linewidth=1,
            arg="UI"
        )
        
        sim.AnimateText(
            text="Live Orders Status",
            x=870, y=575,
            textcolor="lightgreen", fontsize=14
        )
        
        # Function to render the last 25 lines of the order log
        def get_log_text(t):
            lines = self.live_order_log[-25:]
            return "\n".join(lines)
            
        sim.AnimateText(
            text=get_log_text,
            x=870, y=550,
            textcolor="lightgray", fontsize=9, # Reduced slightly to fit status
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

        # 6. Spawn Warmup Manager
        self.warmup_manager = WarmupManager(engine=self, warmup_time=WARMUP_MIN)

    def finalize_metrics(self):
        """Aggregates all component-level data into the central metrics object."""
        import numpy as np
        
        # 0. Record simulation period
        self.metrics.warmup_min = WARMUP_MIN
        self.metrics.sim_duration_min = self.env.now() - WARMUP_MIN

        # 1. Aggregate Order counts (Only those arrived after warmup)
        valid_orders = [o for o in self.order_generator.orders if o.arrival_min >= WARMUP_MIN]
        self.metrics.total_orders_generated = len(valid_orders)

        # 2. Aggregate Server data (Orders completed and fulfillment times)
        all_valid_completed = []
        for server in self.servers:
            # Filter orders by arrival time to exclude warmup bias
            valid_completed = [o for o in server.processed_orders if o.arrival_min >= WARMUP_MIN]
            all_valid_completed.extend(valid_completed)
            self.metrics.total_orders_completed += len(valid_completed)
            for order in valid_completed:
                fulfillment_time = order.completion_time - order.arrival_min
                self.metrics.order_fulfillment_times.append(fulfillment_time)

        # 3. Pending & In-Progress orders
        self.metrics.pending_orders = sum(1 for o in self.order_queue if o.arrival_min >= WARMUP_MIN)
        self.metrics.in_progress_orders = (
            self.metrics.total_orders_generated - 
            self.metrics.pending_orders - 
            self.metrics.total_orders_completed
        )

        # 4. KPI: Optimization Targets
        if all_valid_completed:
            self.metrics.total_mass_delivered = sum(o.item.weight for o in all_valid_completed)
        self.metrics.total_distance_traveled = sum(agv.total_distance for agv in self.agvs)

        # 5. KPI: Service Level Objectives
        # Throughput
        if all_valid_completed:
            hourly_counts = {}
            for o in all_valid_completed:
                hr = int((o.completion_time - WARMUP_MIN) // 60)
                hourly_counts[hr] = hourly_counts.get(hr, 0) + 1
            if hourly_counts:
                self.metrics.peak_throughput_hr = max(hourly_counts.values())
        
        # Min SoC
        self.metrics.min_fleet_soc = min(agv.soc_monitor.minimum() for agv in self.agvs if agv.soc_monitor.number_of_entries() > 0)

        # 6. KPI: Diagnostic Metrics
        assigned_orders = [o for o in valid_orders if o.assignment_min is not None]
        if assigned_orders:
            self.metrics.batching_delays = [o.assignment_min - o.arrival_min for o in assigned_orders]
        
        # Average packing queue time from servers
        queue_means = [server.queue.length_of_stay.mean() for server in self.servers if server.queue.length_of_stay.number_of_entries() > 0]
        if queue_means:
            self.metrics.avg_packing_queue_min = np.mean(queue_means)

        self.metrics.total_stops = sum(agv.total_stops for agv in self.agvs)
        self.metrics.total_tasks_completed = sum(agv.tasks_completed for agv in self.agvs)

        # 7. Aggregate AGV data (Energy and Time Breakdown)
        for agv in self.agvs:
            self.metrics.energy_consumed_wh += agv.total_energy_consumed
            
            # mode is a monitor. weight() gives the total time spent in a given string value
            total_time = self.metrics.sim_duration_min
            moving_pct = (agv.mode.value_duration("MOVING") / total_time * 100) if total_time > 0 else 0
            idle_pct = (agv.mode.value_duration("IDLE") / total_time * 100) if total_time > 0 else 0
            charging_pct = (agv.mode.value_duration("CHARGING") / total_time * 100) if total_time > 0 else 0
            
            min_soc = agv.soc_monitor.minimum() if agv.soc_monitor.number_of_entries() > 0 else agv.soc

            self.metrics.agv_metrics[agv.agv_id] = {
                "energy": agv.total_energy_consumed,
                "tasks": agv.tasks_completed,
                "min_soc": min_soc,
                "moving_pct": moving_pct,
                "idle_pct": idle_pct,
                "charging_pct": charging_pct
            }

    def run(self, till: float):
        """Executes the simulation for the specified duration."""
        self.env.run(till=till)
        self.finalize_metrics()

