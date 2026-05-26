"""
AGV simulation component and state models.
"""

import salabim as sim
import networkx as nx
from enum import Enum


class AGVStatus(Enum):
    """Possible AGV states."""
    IDLE = "IDLE"
    MOVING = "MOVING"
    LOADING = "LOADING"
    UNLOADING = "UNLOADING"
    CHARGING = "CHARGING"


class AGV(sim.Component):
    """ Simulates an AGV navigating the warehouse grid."""

    def setup(self, agv_id: int, routing_graph, server_queue: sim.Queue, charger_queue: sim.Queue) -> None:
        """
        :param agv_id: Unique identifier for the AGV.
        :type agv_id: int
        :param routing_graph: The custom graph representing the warehouse floor.
        :type routing_graph: src.models.graph.RoutingGraph
        :param server_queue: The queue component for the packing area server.
        :type server_queue: sim.Queue
        :param charger_queue: The queue component for the charging station.
        :type charger_queue: sim.Queue
        """
        self.agv_id = agv_id
        self.routing_graph = routing_graph
        self.graph = routing_graph._graph  # Underlying networkx graph for animation data
        self.server_queue = server_queue
        self.charger_queue = charger_queue

        # AGV Parameters
        self.max_battery = 621.6
        self.soc = self.max_battery
        self.soc_threshold = 62.16
        self.drive_speed = 3.5
        self.e_base = 0.0489
        self.e_alpha = 0.0001

        # State tracking
        self.status = AGVStatus.IDLE
        self.current_task = None
        self.payload_mass = 0.0

        # Positioning variables
        self.current_node = 1
        self.next_node = 1

        self.pic = sim.AnimateRectangle(
            spec=(-15, -15, 15, 15),
            x=self.x,
            y=self.y,
            fillcolor=self.color,
            text=str(self.agv_id),
            textcolor="white"
        )

    def x(self, t: float) -> float:
        """Calculates interpolated X coordinate for animation."""
        if self.mode() == "MOVING":
            x_start = self.graph.nodes[self.current_node]['pos'][0]
            x_end = self.graph.nodes[self.next_node]['pos'][0]
            return sim.interpolate(t, self.mode_time(), self.scheduled_time(), x_start, x_end)
        return self.graph.nodes[self.current_node]['pos'][0]

    def y(self, t: float) -> float:
        """Calculates interpolated Y coordinate for animation."""
        if self.mode() == "MOVING":
            y_start = self.graph.nodes[self.current_node]['pos'][1]
            y_end = self.graph.nodes[self.next_node]['pos'][1]
            return sim.interpolate(t, self.mode_time(), self.scheduled_time(), y_start, y_end)
        return self.graph.nodes[self.current_node]['pos'][1]

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

    def process(self):
        """Main lifecycle loop of the AGV component."""
        from src.models.graph import NodeType

        # Find charging node dynamically using underlying nx graph
        charger_node = next(
            (n for n, d in self.graph.nodes(data=True) if d.get('type') == NodeType.CHARGING),
            None
        )

        while True:
            self.status = AGVStatus.IDLE
            while self.current_task is None:
                self.passivate(mode="IDLE")

            self.status = AGVStatus.MOVING
            self.drive_route(self.current_task.pickup_route)

            self.status = AGVStatus.LOADING
            self.hold(self.current_task.pick_time, mode="LOADING")
            self.payload_mass = self.current_task.item_weight

            self.status = AGVStatus.MOVING
            self.drive_route(self.current_task.dropoff_route)

            self.status = AGVStatus.UNLOADING
            self.enter(self.server_queue)
            self.passivate(mode="UNLOADING")

            self.current_task = None
            self.payload_mass = 0.0

            if self.soc < self.soc_threshold:
                if charger_node is not None:
                    self.status = AGVStatus.CHARGING
                    self.drive_route(
                        self.routing_graph.get_shortest_path(self.current_node, charger_node))
                    self.enter(self.charger_queue)
                    self.passivate(mode="CHARGING")
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
            travel_time = dist / self.drive_speed

            self.hold(travel_time, mode="MOVING")

            energy_used = (self.e_base + (self.e_alpha * self.payload_mass)) * dist
            self.soc -= energy_used

        self.current_node = route_node_ids[-1]