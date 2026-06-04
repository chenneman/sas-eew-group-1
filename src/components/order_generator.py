"""Order arrival generator for the warehouse fulfilment DES."""

import random
import salabim as sim

from src.config import SIM_START_HOUR, ORDER_RATE_MULTIPLIER
from src.entities.order import Order

ORDERS_PER_HOUR = [
    13.0,  7.5,  5.0,  4.5,  4.0,  4.0,   # 00-05
     5.0,  8.0, 16.0, 24.0, 30.0, 32.0,   # 06-11
    29.5, 32.0, 32.0, 32.0, 32.5, 30.0,   # 12-17
    28.0, 30.0, 30.5, 30.5, 28.0, 21.0,   # 18-23
]

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
            
            if self.live_order_log is not None:
                # Store order reference to update status later
                log_entry = {
                    "order_id": order.order_id,
                    "time": self.env.now(),
                    "item_name": item.name[:10],
                    "weight": item.weight,
                    "status": "GEN"
                }
                
                def format_log(e):
                    return f"[{e['time']:5.1f}] #{e['order_id']} {e['item_name']} {e['weight']}kg | {e['status']}"
                
                # We'll just append the formatted string for now, but allow external updates via shared list
                self.live_order_log.append(format_log(log_entry))
                # Store the entry for potential updates (though list of strings is simpler for Salabim)
                # Let's stick to strings but make them more descriptive.
            
            # 3. Store and emit
            self.orders.append(order)
            if self.order_queue is not None:
                self.order_queue.append(order)
                
            # Wake up the control system if it's waiting for orders
            if self.control_system and self.control_system.ispassive():
                self.control_system.activate()
