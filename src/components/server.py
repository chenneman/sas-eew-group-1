"""Packing-area server component for processing AGV deliveries."""

import salabim as sim
import logging

from src.components.agv import AGVStatus
from src.environment.service_time_generator import ServiceTimeGenerator
from src.config import SERVICE_TIME_MULTIPLIER

logger = logging.getLogger(__name__)


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
        self.service_time_stats = {}
        
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

                #verification
                for order in self.current_task.orders:
                    order.event_log.append(
                        (self.env.now(), f"Arrived at Server {self.server_id}; unloading started")
                    )
                
                #old model
                logger.debug(f"[Server {self.server_id}] Starting unloading AGV {self.current_agv.agv_id}")
                
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
                
                # ServiceTimeGenerator returns seconds, convert to minutes and apply multiplier
                agv_time_sec, op_time_sec = self.service_time_generator.sample_service_time(n_items)
                agv_time = (agv_time_sec * SERVICE_TIME_MULTIPLIER) / 60.0
                self.remaining_op_time = max(0.0, ((op_time_sec * SERVICE_TIME_MULTIPLIER) / 60.0) - agv_time)

                #additional for verification
                total_service_time = (op_time_sec * SERVICE_TIME_MULTIPLIER) / 60.0
                if n_items not in self.service_time_stats:
                    self.service_time_stats[n_items] = []

                self.service_time_stats[n_items].append(total_service_time)   

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

                for order in self.current_task.orders:
                    order.event_log.append(
                        (self.env.now(), f"Delivered to Server {self.server_id}; AGV released")
                    )
                
                # Move to packing phase
                if self.remaining_op_time > 0:
                    self.state = "PACKING"
                    #verification
                    for order in self.current_task.orders:
                        order.event_log.append(
                            (self.env.now(), f"Packing started at Server {self.server_id}")
                        )
                        
                    self.hold(self.remaining_op_time, mode="PACKING")

                    

                    #old model
                    self.hold(self.remaining_op_time, mode="PACKING")
                    continue
                else:
                    # No packing time left, jump straight to finish
                    self.state = "FINISHING"
                    self.hold(0)
                    continue
                    
            elif self.state == "PACKING" or self.state == "FINISHING":
                #verification
                for order in self.current_task.orders:
                    order.event_log.append(
                        (self.env.now(), f"Finishing at Server {self.server_id}")
                    )
                # Job is completely done
                if self.current_task:
                    logger.info(f"[Server {self.server_id}] Finished processing {len(self.current_task.orders)} orders from AGV {self.current_agv.agv_id if self.current_agv else 'unknown'}")
                    for order in self.current_task.orders:
                        order.status = "COMPLETED"
                        order.completion_time = self.env.now()
                        order.event_log.append((self.env.now(), f"Completed at Server {self.server_id}")) #additional for verification
                        self.processed_orders.append(order)
                        
                self.current_agv = None
                self.current_task = None
                self.state = "IDLE"
                
                # Immediately loop back to check queue
                self.hold(0)
                continue
