"""Order arrival generator for the warehouse fulfilment DES."""

import random
import salabim as sim
import logging

logger = logging.getLogger(__name__)

from src.config import SIM_START_HOUR, ORDER_RATE_MULTIPLIER
from src.entities.order import Order

#ORDERS_PER_HOUR = [
#    13.0,  7.5,  5.0,  4.5,  4.0,  4.0,   # 00-05
#     5.0,  8.0, 16.0, 24.0, 30.0, 32.0,   # 06-11
#    29.5, 32.0, 32.0, 32.0, 32.5, 30.0,   # 12-17
#    28.0, 30.0, 30.5, 30.5, 28.0, 21.0,   # 18-23
#]

ORDERS_PER_HOUR = [
    25.286240, 14.145563, 9.022052, 7.804150,7.156685,6.862044,9.618115,
    15.602688, 30.774819, 47.333230, 59.971362, 63.864598, 58.204358, 62.753838,
    63.034389, 61.623276, 63.945139, 59.013776, 55.635515, 58.274353, 60.126703,
    60.157166, 55.995140, 40.854802
]

#For verification
#ORDERS_PER_HOUR = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,]


# ── Helper functions ──────────────────────────────────────────────────────────

def mean_iat_minutes(sim_minute: float) -> float:
    """Mean inter-arrival time [min] for the current simulation time."""
    real_hour = int(SIM_START_HOUR + sim_minute // 60) % 24
    lam = ORDERS_PER_HOUR[real_hour] * ORDER_RATE_MULTIPLIER
    return 60.0 / lam if lam > 0 else 60.0

# ── OrderGenerator ────────────────────────────────────────────────────────────

class OrderGenerator(sim.Component):
    """Salabim component that generates orders according to ORDERS_PER_HOUR rates.

    This component samples an inter-arrival time, waits, and then creates a new
    Order object, assigning it a unique sequential ID.
    """

    def setup(self, items: list, order_queue: list | None = None, control_system: sim.Component | None = None, live_order_log: list = None):
        """
        Setup the generator state.
        
        Args:
            items: Sequence of Item objects to sample from.
            order_queue: Optional list where generated orders are appended.
            control_system: Optional reference to the ControlSystem to wake up.
            live_order_log: Optional list to store string representations of generated orders.
        """
        self.items = items
        self.order_queue = order_queue
        self.control_system = control_system
        self.live_order_log = live_order_log
        
        # Internal state tracking (Replaces the shared TOrder._next_id)
        self.orders_generated: int = 0
        self.orders: list[Order] = []

    def process(self):
        """Main generator loop. (Salabim yieldless paradigm)."""
        if sum(ORDERS_PER_HOUR) == 0:        
            return
        
        while True:
            # 1. Sample inter-arrival time
            mean_iat = mean_iat_minutes(self.env.now())
            iat = self.env.Exponential(mean_iat).sample()
            
            # Wait for the next arrival
            self.hold(iat)
            
            # 2. Generate the order
            self.orders_generated += 1
            item = self.env.random.choice(self.items)
            
            order = Order(
                order_id=self.orders_generated,
                item=item,
                arrival_min=self.env.now()
            )
            order.event_log.append((self.env.now(), "Order generated")) #additional for verification
            logger.info(f"[OrderGenerator] New Order #{order.order_id} generated: {item.name[:20]} ({item.weight}kg)")
            
            if self.live_order_log is not None:
                # Store the raw Order object directly for UI reactivity
                self.live_order_log.append(order)
            
            # 3. Store and emit
            self.orders.append(order)
            if self.order_queue is not None:
                self.order_queue.append(order)
                
            # Wake up the control system if it's waiting for orders
            if self.control_system and self.control_system.ispassive():
                self.control_system.activate()
    
    # def process(self):
    #     """Mini verification scenario: generate exactly five orders."""
    #     arrival_times = [1.0, 1.5, 1.8, 6.0, 12.0]
    #     for arrival_time in arrival_times:
    #         # Wait until the next scheduled arrival
    #         self.hold(arrival_time - self.env.now())
    #         self.orders_generated += 1
    #         item = self.items[self.orders_generated - 1]
    #         order = Order(
    #             order_id=self.orders_generated,
    #             item=item,
    #             arrival_min=self.env.now()
    #         )
    #         order.event_log.append(
    #             (self.env.now(), "Order generated")
    #         )
    #         logger.info(
    #             f"[Verification] New Order #{order.order_id} generated: "
    #             f"{item.name[:20]} ({item.weight}kg)"
    #         )
    #         if self.live_order_log is not None:
    #             self.live_order_log.append(order)
    #         self.orders.append(order)
    #         if self.order_queue is not None:
    #             self.order_queue.append(order)
    #         if self.control_system and self.control_system.ispassive():
    #             self.control_system.activate()
    #     return
