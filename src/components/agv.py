"""
AGV simulation component and state models.
"""

import salabim as sim
from enum import Enum

from src.environment.graph import NodeType
from src.config import MAX_BATTERY, BATTERY_THRESHOLD, DRIVE_SPEED, E_BASE, ALPHA
from src.utils.animation import grid_to_pixel


class AGVStatus(Enum):
    """Possible AGV states."""
    IDLE = "IDLE"
    MOVING = "MOVING"
    LOADING = "LOADING"
    UNLOADING = "UNLOADING"
    CHARGING = "CHARGING"


class AGV(sim.Component):
    """ Simulates an AGV navigating the warehouse grid."""

    def setup(self, agv_id: int, routing_graph, server_queue: sim.Queue, charger_queue: sim.Queue, available_agvs: sim.Queue, queue_to_component: dict | None = None, charger_queues_map: dict | None = None, packing_queues_map: dict | None = None) -> None:
        """
        :param agv_id: Unique identifier for the AGV.
        :type agv_id: int
        :param routing_graph: The custom graph representing the warehouse floor.
        :type routing_graph: src.models.graph.RoutingGraph
        :param server_queue: The queue component for the packing area server.
        :type server_queue: sim.Queue
        :param charger_queue: The queue component for the charging station.
        :type charger_queue: sim.Queue
        :param available_agvs: The queue managed by the ControlSystem for idle AGVs.
        :type available_agvs: sim.Queue
        :param queue_to_component: Optional mapping to wake up passive components.
        :type queue_to_component: dict
        :param charger_queues_map: Optional mapping of node IDs to specific charger queues.
        :type charger_queues_map: dict
        :param packing_queues_map: Optional mapping of node IDs to specific server queues.
        :type packing_queues_map: dict
        """
        self.agv_id = agv_id
        self.routing_graph = routing_graph
        self.graph = routing_graph._graph  # Underlying networkx graph for animation data
        self.server_queue = server_queue
        self.charger_queue = charger_queue
        self.available_agvs = available_agvs
        self.queue_to_component = queue_to_component or {}
        self.charger_queues_map = charger_queues_map or {}
        self.packing_queues_map = packing_queues_map or {}

        # AGV Parameters
        self.battery = MAX_BATTERY

        # Metrics tracking
        self.total_energy_consumed = 0.0
        self.tasks_completed = 0
        self.total_distance = 0.0
        self.total_stops = 0
        self.soc_monitor = sim.Monitor(name=f"soc_agv_{agv_id}")

        # State tracking
        self.status = AGVStatus.IDLE
        self.current_task = None
        self.payload_mass = 0.0
        self.items_loaded = 0

        # Positioning variables
        self.current_node = 1
        self.next_node = 1

        self.pic = sim.AnimateRectangle(
            spec=(-15, -15, 15, 15),
            x=self.x,
            y=self.y,
            fillcolor=self.color
        )
        
        # Background for text to make it readable on any surface
        # Center the rectangle exactly at (x, y-40) with a width of 50 and height of 30
        self.text_bg = sim.AnimateRectangle(
            spec=(-25, -15, 25, 15), # Width 50, Height 30, centered at 0,0 locally
            x=self.x,
            y=lambda t: self.y(t) - 40,
            fillcolor=("black", 153) # 153 is 0.6 * 255
        )

        self.text_pic = sim.AnimateText(
            text=self.get_anim_text,
            x=self.x,
            y=lambda t: self.y(t) - 40,
            textcolor="white",
            fontsize=10,
            text_anchor="c" # Correct Salabim keyword for centering text
        )

    def _wakeup_component(self, queue: sim.Queue):
        """Activates the component(s) associated with a queue if they are passive."""
        target = self.queue_to_component.get(queue)
        if not target:
            return

        # Handle both single components (ControlSystem) and lists (Servers/Chargers)
        targets = target if isinstance(target, list) else [target]
        for comp in targets:
            if comp.ispassive():
                comp.activate()

    @property
    def soc(self) -> float:
        """Percentage of battery remaining."""
        return self.battery / MAX_BATTERY * 100

    def get_anim_text(self, t: float) -> str:
        """Dynamically generates the text to display above the AGV."""
        return f"AGV{self.agv_id}\nBat:{self.soc:.0f}%\nItems:{self.items_loaded}"

    def x(self, t: float) -> float:
        """Calculates interpolated X coordinate for animation."""
        if self.mode() == "MOVING":
            x_start = grid_to_pixel(self.graph.nodes[self.current_node]['pos'][0])
            x_end = grid_to_pixel(self.graph.nodes[self.next_node]['pos'][0])
            return sim.interpolate(t, self.mode_time(), self.scheduled_time(), x_start, x_end)
        return grid_to_pixel(self.graph.nodes[self.current_node]['pos'][0])

    def y(self, t: float) -> float:
        """Calculates interpolated Y coordinate for animation."""
        if self.mode() == "MOVING":
            y_start = grid_to_pixel(self.graph.nodes[self.current_node]['pos'][1])
            y_end = grid_to_pixel(self.graph.nodes[self.next_node]['pos'][1])
            return sim.interpolate(t, self.mode_time(), self.scheduled_time(), y_start, y_end)
        return grid_to_pixel(self.graph.nodes[self.current_node]['pos'][1])

    def color(self, t: float) -> str:
        """Determines animation color based on AGV status."""
        colors = {
            AGVStatus.IDLE: "gray",
            AGVStatus.MOVING: "green",
            AGVStatus.LOADING: "yellow",
            AGVStatus.UNLOADING: "orange",
            AGVStatus.CHARGING: "red"
        }
        return colors.get(self.status, "black")

    def complete_task(self):
        """Cleans up the current task state. Called by the Server after unloading."""
        self.current_task = None
        self.payload_mass = 0.0
        self.items_loaded = 0
        self.tasks_completed += 1

    def process(self):
        """Main lifecycle loop of the AGV component."""
        import networkx as nx

        # Find all charging nodes
        charger_nodes = [
            n for n, d in self.graph.nodes(data=True) if d.get('type') == NodeType.CHARGING
        ]
        
        # Find idle nodes
        idle_nodes = [n for n, d in self.graph.nodes(data=True) if d.get('type') == NodeType.IDLE]

        while True:
            self.status = AGVStatus.IDLE
            self.enter(self.available_agvs)
            self._wakeup_component(self.available_agvs)
            
            # If not at an idle node, move to one
            if self.current_node not in idle_nodes and idle_nodes:
                # Pick an idle node (ideally one that matches agv_id to avoid overlap)
                target_idle = idle_nodes[(self.agv_id - 1) % len(idle_nodes)]
                path = self.routing_graph.get_shortest_path(self.current_node, target_idle)
                self.status = AGVStatus.MOVING
                self.drive_route(path)
                self.status = AGVStatus.IDLE
            
            while self.current_task is None:
                self.passivate(mode="IDLE")
            
            if self in self.available_agvs:
                self.leave(self.available_agvs)

            for pickup in self.current_task.pickups:
                self.status = AGVStatus.MOVING
                self.drive_route(pickup.route)

                self.status = AGVStatus.LOADING
                self.hold(pickup.pick_time, mode="LOADING")
                
                # Dynamically accumulate mass and items
                for item in pickup.items:
                    self.payload_mass += item.weight
                    self.items_loaded += 1

            self.status = AGVStatus.MOVING
            self.drive_route(self.current_task.dropoff_route)

            self.status = AGVStatus.UNLOADING
            
            # Use specific server queue if available based on dropoff route's final node
            target_server_queue = self.server_queue
            final_node = self.current_task.dropoff_route[-1]
            if hasattr(self, 'packing_queues_map') and final_node in self.packing_queues_map:
                target_server_queue = self.packing_queues_map[final_node]

            self.enter(target_server_queue)
            self._wakeup_component(target_server_queue)
            self.passivate(mode="UNLOADING")

            if self.battery < BATTERY_THRESHOLD:
                if charger_nodes:
                    # Find the optimal charger: closest distance + penalty for queue length
                    # High penalty ensures AGVs always pick an empty charger if one exists
                    QUEUE_PENALTY = 1000.0
                    
                    def score_charger(node_id):
                        dist = nx.shortest_path_length(self.graph, self.current_node, node_id, weight='weight')
                        q_length = 0
                        if hasattr(self, 'charger_queues_map') and node_id in self.charger_queues_map:
                            q_length = len(self.charger_queues_map[node_id])
                        return dist + (q_length * QUEUE_PENALTY)

                    charger_node = min(charger_nodes, key=score_charger)
                    
                    # Use specific queue if available, fallback to shared
                    target_queue = self.charger_queue
                    if hasattr(self, 'charger_queues_map') and charger_node in self.charger_queues_map:
                        target_queue = self.charger_queues_map[charger_node]
                        
                    self.enter(target_queue) # Enter queue immediately to reserve spot and update length
                    
                    print(f"[AGV {self.agv_id}] Low battery ({self.soc:.1f}%). Moving to charger {charger_node}...")
                    self.status = AGVStatus.CHARGING
                    self.drive_route(
                        self.routing_graph.get_shortest_path(self.current_node, charger_node))
                        
                    self._wakeup_component(target_queue) # Wakeup the specific charger
                    self.passivate(mode="CHARGING")
                    print(f"[AGV {self.agv_id}] Charging complete. Battery: {self.soc:.1f}%.")
                else:
                    # Fallback or warning if no charger found
                    print(f"Warning: AGV {self.agv_id} low battery but no charger found in graph.")



    def drive_route(self, route_node_ids: list[int]):
        """
        Method to handle dynamic edge-by-edge movement and energy calculations.

        :param route_node_ids: List of sequential node IDs representing the path.
        :type route_node_ids: list[int]
        """
        for i in range(len(route_node_ids) - 1):
            self.current_node = route_node_ids[i]
            self.next_node = route_node_ids[i + 1]

            dist = self.graph[self.current_node][self.next_node]['weight']
            self.total_distance += dist
            self.total_stops += 1
            
            # dist [m] / speed [m/s] = time [s] -> convert to [min]
            travel_time = (dist / DRIVE_SPEED) / 60.0

            self.hold(travel_time, mode="MOVING")

            energy_used = (E_BASE + (ALPHA * self.payload_mass)) * dist
            self.battery -= energy_used
            self.total_energy_consumed += energy_used
            self.soc_monitor.tally(self.soc)

        self.current_node = route_node_ids[-1]