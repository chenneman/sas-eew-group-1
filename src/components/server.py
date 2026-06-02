"""Packing-area server component for processing AGV deliveries."""

import salabim as sim

from components.agv import AGVStatus
from environment.service_time_generator import ServiceTimeGenerator


class Server(sim.Component):
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
        self.queue = queue
        self.service_time_generator = service_time_generator or ServiceTimeGenerator()
        self.processed_orders = processed_orders if processed_orders is not None else []
        self.poll_interval = poll_interval
        self.location = location
        
        # State machine variables
        self.state = "IDLE"
        self.current_agv = None
        self.current_task = None
        self.remaining_op_time = 0.0

    def process(self):
        # Pure Yieldless State Machine
        while True:
            if self.state == "IDLE":
                if len(self.queue) == 0:
                    self.passivate()
                    continue
                    
                # Start serving
                self.state = "UNLOADING"
                self.current_agv = self.queue.pop()
                self.current_task = self.current_agv.current_task
                
                if not self.current_task:
                    # Invalid state, clean up and reset
                    self.current_agv.status = AGVStatus.IDLE
                    self.current_agv.activate()
                    self.current_agv = None
                    self.current_task = None
                    self.state = "IDLE"
                    self.hold(0) # Re-evaluate immediately
                    continue
                    
                all_items = self.current_task.all_items
                n_items = len(all_items)
                
                agv_time, op_time = self.service_time_generator.sample_service_time(n_items)
                self.remaining_op_time = max(0.0, op_time - agv_time)
                
                for item in all_items:
                    item.status = "DELIVERED"
                    
                self.hold(agv_time, mode="UNLOADING")
                continue
                
            elif self.state == "UNLOADING":
                # AGV is done, release it
                if hasattr(self.current_agv, "complete_task"):
                    self.current_agv.complete_task()
                self.current_agv.status = AGVStatus.IDLE
                self.current_agv.activate()
                
                # Move to packing phase
                if self.remaining_op_time > 0:
                    self.state = "PACKING"
                    self.hold(self.remaining_op_time, mode="PACKING")
                    continue
                else:
                    # No packing time left, jump straight to finish
                    self.state = "FINISHING"
                    self.hold(0)
                    continue
                    
            elif self.state == "PACKING" or self.state == "FINISHING":
                # Job is completely done
                if self.current_task:
                    for order in self.current_task.orders:
                        order.status = "COMPLETED"
                        order.completion_time = self.env.now()
                        self.processed_orders.append(order)
                        
                self.current_agv = None
                self.current_task = None
                self.state = "IDLE"
                
                # Immediately loop back to check queue
                self.hold(0)
                continue
