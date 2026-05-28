"""Charging-station component for AGVs."""

from __future__ import annotations

import salabim as sim

from src.models.agv import AGVStatus


class TCharger(sim.Component):
    """Charges AGVs and releases the fullest AGV first when multiple are waiting."""

    def setup(
        self,
        charger_id: int,
        queue: sim.Queue,
        routing_graph=None,
        idle_node_id: int | None = None,
        charging_rate: float = 10.0,
        poll_interval: float = 1.0,
        location=None,
    ) -> None:
        self.charger_id = charger_id
        self.MyQueue = queue
        self.queue = self.MyQueue
        self.my_queue = self.MyQueue
        self.routing_graph = routing_graph
        self.idle_node_id = idle_node_id
        self.charging_rate = charging_rate
        self.poll_interval = poll_interval
        self.location = location
        self.busy = False

    def process(self):
        while True:
            while len(self.MyQueue) == 0:
                yield self.hold(self.poll_interval, mode="IDLE")

            self.busy = True
            agv = self.best_charged_agv()
            agv.leave(self.MyQueue)
            agv.status = AGVStatus.CHARGING

            charging_time = self.time_to_full(agv)
            if charging_time > 0:
                yield self.hold(charging_time, mode="CHARGING")

            agv.soc = self.max_battery(agv)
            self.move_agv_to_idle_spot(agv)
            agv.status = AGVStatus.IDLE
            agv.activate()
            self.busy = False

    def best_charged_agv(self):
        """Select the AGV with the highest battery percentage from the charger queue."""
        return max(list(self.MyQueue), key=self.battery_percentage)

    def battery_percentage(self, agv) -> float:
        maximum = self.max_battery(agv)
        if maximum <= 0:
            return 0.0
        return getattr(agv, "soc", 0.0) / maximum

    def max_battery(self, agv) -> float:
        return float(getattr(agv, "max_battery", 100.0))

    def time_to_full(self, agv) -> float:
        missing_charge = max(0.0, self.max_battery(agv) - getattr(agv, "soc", 0.0))
        if self.charging_rate <= 0:
            raise ValueError("charging_rate must be greater than 0")
        return missing_charge / self.charging_rate

    def move_agv_to_idle_spot(self, agv) -> None:
        """Place a fully charged AGV at the configured idle node."""
        idle_node = self.resolve_idle_node(agv)
        if idle_node is None:
            return

        if self.routing_graph is not None and hasattr(agv, "current_node"):
            try:
                route = self.routing_graph.get_shortest_path(agv.current_node, idle_node)
            except Exception:
                route = [idle_node]

            if hasattr(agv, "route"):
                agv.route = route

        if hasattr(agv, "current_node"):
            agv.current_node = idle_node
        if hasattr(agv, "next_node"):
            agv.next_node = idle_node

    def resolve_idle_node(self, agv) -> int | None:
        if self.idle_node_id is not None:
            return self.idle_node_id

        graph = getattr(agv, "graph", None)
        if graph is None and self.routing_graph is not None:
            graph = getattr(self.routing_graph, "_graph", None)
        if graph is None:
            return None

        return next(
            (node for node, data in graph.nodes(data=True) if self.is_idle_node_type(data.get("type"))),
            None,
        )

    def is_idle_node_type(self, node_type) -> bool:
        """Support both NodeType.IDLE and simple string-based test graphs."""
        return node_type == "IDLE" or getattr(node_type, "name", None) == "IDLE"
