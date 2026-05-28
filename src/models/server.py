"""Packing-area server component for processing AGV deliveries."""

from __future__ import annotations

import salabim as sim

from src.models.agv import AGVStatus
from src.models.service_time_generator import ServiceTimeGenerator


class TServer(sim.Component):
    """Processes AGVs waiting at the packing area."""

    def setup(
        self,
        server_id: int,
        queue: sim.Queue,
        service_time_generator: ServiceTimeGenerator | None = None,
        processed_orders: list | None = None,
        poll_interval: float = 1.0,
        location=None,
    ) -> None:
        self.server_id = server_id
        self.MyQueue = queue
        self.queue = self.MyQueue
        self.my_queue = self.MyQueue
        self.service_time_generator = service_time_generator or ServiceTimeGenerator()
        self.processed_orders = processed_orders if processed_orders is not None else []
        self.poll_interval = poll_interval
        self.location = location
        self.busy = False

    def process(self):
        while True:
            while len(self.MyQueue) == 0:
                yield self.hold(self.poll_interval, mode="IDLE")

            self.busy = True
            my_agv = self.first_of_queue()
            my_agv.leave(self.MyQueue)
            task = getattr(my_agv, "current_task", None)
            orders = self.get_orders_from_task(task)
            all_items = self.gather_all_items(orders)

            if not all_items:
                all_items = self.gather_all_items_from_task(task)

            _, op_time = self.sample_service_time(len(all_items))
            yield self.hold(op_time, mode="SERVING")

            for item in all_items:
                item.status = "DELIVERED"

            for order in orders:
                if self.all_items_delivered(order):
                    order.status = "COMPLETED"
                    order.completion_time = self.env.now()
                    order.CompletionTime = self.env.now()
                    self.save_order_data(order)

            my_agv.current_task = None
            if hasattr(my_agv, "route"):
                my_agv.route = []
            if hasattr(my_agv, "orders"):
                my_agv.orders = []
            if hasattr(my_agv, "payload_mass"):
                my_agv.payload_mass = 0.0
            if hasattr(my_agv, "items_loaded"):
                my_agv.items_loaded = 0
            my_agv.status = AGVStatus.IDLE
            my_agv.activate()
            self.busy = False

    def first_of_queue(self):
        """Return the first AGV in MyQueue, matching the PDL FirstofQueue step."""
        return self.MyQueue[0]

    def sample_service_time(self, n_items: int) -> tuple[float, float]:
        """Sample AGV and operator service time for the given number of items."""
        return self.service_time_generator.sample_service_time(n_items)

    def gather_all_items(self, orders) -> list:
        """Collect all items from a list of orders."""
        items = []
        for order in orders:
            if hasattr(order, "items"):
                items.extend(order.items)
            elif hasattr(order, "item"):
                items.append(order.item)
        return items

    def gather_all_items_from_task(self, task) -> list:
        """Fallback for task models that store items directly instead of via orders."""
        if task is None:
            return []
        if hasattr(task, "items"):
            return list(task.items)
        if hasattr(task, "all_items"):
            return list(task.all_items)
        return []

    def get_orders_from_task(self, task) -> list:
        """Return the orders belonging to an AGV task."""
        if task is not None and hasattr(task, "orders"):
            return list(task.orders)
        return []

    def all_items_delivered(self, order) -> bool:
        """Check whether every item in an order has status DELIVERED."""
        return all(
            getattr(item, "status", None) == "DELIVERED"
            for item in self.gather_all_items([order])
        )

    def save_order_data(self, order) -> None:
        """Store completed orders for later KPI analysis."""
        self.processed_orders.append(order)
