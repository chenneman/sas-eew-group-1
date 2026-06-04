"""
Core Simulation Engine.
Orchestrates the setup and execution of the Salabim environment and all components.
"""

import logging
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
    ENABLE_UI_LOGGING,
    SIM_START_HOUR,
    WARMUP_MIN,
    LOG_LEVEL
)

from src.utils.paths import LOGS_DIR
from src.utils.logger import UILogHandler

from src.core.metrics import SimulationMetrics

logger = logging.getLogger(__name__)

class WarmupManager(sim.Component):
    """Component that waits for the warmup period and then resets component metrics."""
    def setup(self, engine, warmup_time: float):
        self.engine = engine
        self.warmup_time = warmup_time

    def process(self):
        self.hold(self.warmup_time)
        logger.info(f"--- Warmup Period ({self.warmup_time} min) Finished. Resetting Metrics... ---")
        
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

        # 1. World & Queues must be built before UI
        self._build_world()
        self._instantiate_queues()
        self._boot_components()

        # 2. Setup UI Log Mirroring (only if animating and enabled)
        if self.animate and ENABLE_UI_LOGGING:
            # Create a simple formatter for UI (no colors, no complex date)
            ui_fmt = logging.Formatter("%(levelname)-5s %(message)s")
            self.ui_log_handler = UILogHandler(self.live_event_log, max_lines=25)
            self.ui_log_handler.setFormatter(ui_fmt)
            self.ui_log_handler.setLevel(LOG_LEVEL)
            logging.getLogger().addHandler(self.ui_log_handler)

        if self.animate:
            self.env.animation_parameters(animate=True, speed=INITIAL_ANIM_SPEED, width=1920, height=1080)
            self.env.background_color("black")
            self._build_ui()
            
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures log files and UI handlers are properly closed."""
        if hasattr(self, 'ui_log_handler'):
            logging.getLogger().removeHandler(self.ui_log_handler)
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
        """Creates the on-screen UI overlay for real-time metrics and telemetry."""
        # 1. KPI Panel (Top Left of the UI area)
        sim.AnimateRectangle(
            spec=(860, 700, 1200, 950),
            fillcolor="#1a1a1a",
            linecolor="white",
            linewidth=2,
            arg="UI"
        )
        
        # Clock
        def get_clock_time(t):
            total_mins = self.env.now() + (SIM_START_HOUR * 60)
            hrs = int((total_mins // 60) % 24)
            mins = int(total_mins % 60)
            return f"{hrs:02d}:{mins:02d}"

        sim.AnimateText(text=get_clock_time, x=880, y=920, textcolor="lightgray", fontsize=16, text_anchor="nw")
        
        sim.AnimateText(text=lambda t: f"Sim Time: {self.env.now():.1f} min", x=880, y=890, textcolor="white", fontsize=18, text_anchor="nw")
        
        def get_completed_count(t):
            return f"Completed: {sum(len(s.processed_orders) for s in self.servers)}"
        sim.AnimateText(text=get_completed_count, x=880, y=730, textcolor="cyan", fontsize=18, text_anchor="nw")
        
        sim.AnimateText(text=lambda t: f"Pending: {len(self.order_queue)}", x=880, y=810, textcolor="yellow", fontsize=18, text_anchor="nw")
        
        def get_in_progress(t):
            return f"In-Progress: {self.order_generator.orders_generated - sum(len(s.processed_orders) for s in self.servers) - len(self.order_queue)}"
        sim.AnimateText(text=get_in_progress, x=880, y=770, textcolor="orange", fontsize=18, text_anchor="nw")
        
        def get_active_agvs(t):
            return f"Active AGVs: {sum(1 for a in self.agvs if a.status != AGVStatus.IDLE)}/{len(self.agvs)}"
        sim.AnimateText(text=get_active_agvs, x=1000, y=920, textcolor="white", fontsize=16, text_anchor="nw")

        # Throughput Tracker
        def get_throughput(t):
            hr = self.env.now() / 60
            comp = sum(len(s.processed_orders) for s in self.servers)
            tp = comp / hr if hr > 0 else 0
            return f"Throughput: {tp:.1f} /hr"
        sim.AnimateText(text=get_throughput, x=880, y=850, textcolor="magenta", fontsize=18, text_anchor="nw")

        # 2. Reactive Live Order Log (Bottom Left of the UI area)
        sim.AnimateRectangle(
            spec=(860, 50, 1200, 680),
            fillcolor="#111111",
            linecolor="gray",
            linewidth=1,
            arg="UI"
        )
        sim.AnimateText(text="Live Orders Status", x=870, y=650, textcolor="lightgreen", fontsize=16, text_anchor="nw")

        # Multiple AnimateText loops for colors
        for i in range(25):
            def log_text(t, idx=i):
                if idx < len(self.live_order_log):
                    o = self.live_order_log[-(idx+1)]
                    return f"[{o.arrival_min:5.1f}] #{o.order_id} {o.item.name[:10]} {o.item.weight}kg | {o.status}"
                return ""
                
            def log_color(t, idx=i):
                if idx < len(self.live_order_log):
                    s = self.live_order_log[-(idx+1)].status
                    if s == "GEN": return "white"
                    if s == "ASSIGNED": return "orange"
                    if s == "COMPLETED": return "lightgreen"
                return "gray"
                
            y_pos = 620 - (i * 20)
            sim.AnimateText(
                text=lambda t, idx=i: log_text(t, idx),
                x=870, y=y_pos,
                textcolor=lambda t, idx=i: log_color(t, idx),
                fontsize=11,
                text_anchor="nw"
            )

        # 3. AGV Telemetry Panels (Right of the UI area)
        start_x = 1220
        start_y = 950
        box_w = 300
        box_h = 200
        padding = 20
        
        for idx, agv in enumerate(self.agvs):
            bx = start_x + (idx % 2) * (box_w + padding)
            by = start_y - (idx // 2) * (box_h + padding)
            
            sim.AnimateRectangle(
                spec=(bx, by - box_h, bx + box_w, by),
                fillcolor="#222222",
                linecolor="cyan",
                linewidth=2,
                arg="UI"
            )
            sim.AnimateText(text=f"AGV {agv.agv_id} Telemetry", x=bx+10, y=by-20, textcolor="cyan", fontsize=16, text_anchor="nw")
            
            def agv_soc(t, a=agv): return f"Battery: {a.soc:.1f}%"
            sim.AnimateText(text=lambda t, a=agv: agv_soc(t, a), x=bx+10, y=by-50, textcolor="yellow", fontsize=14, text_anchor="nw")
            
            def agv_stat(t, a=agv): return f"Status: {a.status.name if hasattr(a.status, 'name') else a.status}"
            sim.AnimateText(text=lambda t, a=agv: agv_stat(t, a), x=bx+10, y=by-75, textcolor="white", fontsize=14, text_anchor="nw")
            
            def agv_load(t, a=agv): 
                mass = a.payload_mass if hasattr(a, 'payload_mass') else 0.0
                items = a.items_loaded if hasattr(a, 'items_loaded') else 0
                return f"Load: {mass:.1f}kg ({items} items)"
            sim.AnimateText(text=lambda t, a=agv: agv_load(t, a), x=bx+10, y=by-100, textcolor="lightgray", fontsize=14, text_anchor="nw")
            
            def agv_orders(t, a=agv):
                if not hasattr(a, 'orders') or not a.orders: return "Assigned: None"
                return f"Assigned: {','.join(str(o.order_id) for o in a.orders)}"
            sim.AnimateText(text=lambda t, a=agv: agv_orders(t, a), x=bx+10, y=by-125, textcolor="orange", fontsize=12, text_anchor="nw")
            
            def agv_energy(t, a=agv): 
                energy = a.total_energy_consumed if hasattr(a, 'total_energy_consumed') else 0.0
                return f"Energy: {energy:.1f} Wh"
            sim.AnimateText(text=lambda t, a=agv: agv_energy(t, a), x=bx+10, y=by-150, textcolor="white", fontsize=12, text_anchor="nw")

        # 4. Reactive Live Event Log (Bottom Right)
        # Position it below the AGV telemetry grid
        # For 4 AGVs, telemetry ends at y=530. Let's start log at y=510.
        log_panel_y = 510
        if N_AGV > 4:
             # Adjust if more rows of AGVs exist
             log_panel_y = start_y - ((N_AGV + 1) // 2) * (box_h + padding) + padding

        sim.AnimateRectangle(
            spec=(start_x, 50, 1860, log_panel_y), # Width matching telemetry grid
            fillcolor="#0a0a0a",
            linecolor="cyan",
            linewidth=1,
            arg="UI"
        )
        sim.AnimateText(text="Live Simulation Events (Log)", x=start_x + 10, y=log_panel_y - 25, textcolor="cyan", fontsize=16, text_anchor="nw")

        for i in range(20):
            def event_text(t, idx=i):
                if idx < len(self.live_event_log):
                    return self.live_event_log[-(idx+1)]
                return ""
            
            def event_color(t, idx=i):
                if idx < len(self.live_event_log):
                    line = self.live_event_log[-(idx+1)]
                    if "DEBUG" in line: return "cyan"
                    if "INFO" in line: return "lightgreen"
                    if "WARNING" in line: return "yellow"
                    if "ERROR" in line: return "red"
                return "white"

            y_pos = log_panel_y - 55 - (i * 20)
            sim.AnimateText(
                text=lambda t, idx=i: event_text(t, idx),
                x=start_x + 10, y=y_pos,
                textcolor=lambda t, idx=i: event_color(t, idx),
                fontsize=11,
                text_anchor="nw"
            )

    def _instantiate_queues(self):
        """Creates the central communication queues and component mappings."""
        self.order_queue = [] # Standard list because Orders are passive dataclasses
        self.live_order_log = [] # List of strings for UI display
        self.live_event_log = [] # List of strings for UI log mirroring
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
