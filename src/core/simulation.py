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
    SIM_START_HOUR
)


class SimulationEngine:
    """
    Wraps the Salabim environment and initializes all required simulation entities.
    """

    def __init__(self, trace: bool = False, animate: bool = False):
        self.env = sim.Environment(trace=trace)
        self.animate = animate
        
        if self.animate:
            #  will configure animation parameters here later in Phase 3
            pass

        self._build_world()
        self._instantiate_queues()
        self._boot_components()

    def _build_world(self):
        """Initializes the static warehouse layout and math engines."""
        # Load items (using default paths configured in utils)
        self.items = load_items()
        
        # Build the warehouse map (pure layout, no item injection)
        self.warehouse = Warehouse()
        
        # Initialize math engine
        self.service_time_generator = ServiceTimeGenerator()

    def _instantiate_queues(self):
        """Creates the central communication queues."""
        self.order_queue = [] # Standard list because Orders are passive dataclasses
        self.available_agvs = sim.Queue("available_agvs")
        self.server_queue = sim.Queue("server_queue")
        self.charger_queue = sim.Queue("charger_queue")

    def _boot_components(self):
        """Spawns all active sim.Components."""
        
        # 1. Spawn Control System first so others can reference it
        self.control_system = ControlSystem(
            warehouse=self.warehouse,
            order_queue=self.order_queue,
            available_agvs=self.available_agvs
        )
        
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

        # 4. Spawn Chargers
        self.chargers = []
        for i in range(1, N_CHARGERS + 1):
            charger = Charger(
                charger_id=i,
                queue=self.charger_queue,
                charging_rate=CHARGE_RATE
            )
            self.chargers.append(charger)

        # 5. Spawn AGVs
        self.agvs = []
        for i in range(1, N_AGV + 1):
            agv = AGV(
                agv_id=i,
                routing_graph=self.warehouse.routing_graph,
                server_queue=self.server_queue,
                charger_queue=self.charger_queue,
                available_agvs=self.available_agvs
            )
            self.agvs.append(agv)

        self.control_system.agvs = self.agvs # Inject complete fleet reference

    def run(self, till: float):
        """Executes the simulation for the specified duration."""
        self.env.run(till=till)

