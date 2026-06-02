"""Order arrival generator for the warehouse fulfilment DES."""

import random
import salabim as sim

from src.config import ORDERS_PER_HOUR, SIM_START_HOUR
from src.entities.order import Order

# ── Helper functions ──────────────────────────────────────────────────────────

def mean_iat_minutes(sim_minute: float) -> float:
    """Mean inter-arrival time [min] for the current simulation time."""
    real_hour = int(SIM_START_HOUR + sim_minute // 60) % 24
    lam = ORDERS_PER_HOUR[real_hour]
    return 60.0 / lam if lam > 0 else 60.0

# ── OrderGenerator ────────────────────────────────────────────────────────────

class OrderGenerator(sim.Component):
    """Salabim component that generates orders according to ORDERS_PER_HOUR rates.

    This component samples an inter-arrival time, waits, and then creates a new
    Order object, assigning it a unique sequential ID.
    """

    def setup(self, items: list, order_queue: list | None = None, control_system: sim.Component | None = None):
        """
        Setup the generator state.
        
        Args:
            items: Sequence of Item objects to sample from.
            order_queue: Optional list where generated orders are appended.
            control_system: Optional reference to the ControlSystem to wake up.
        """
        self.items = items
        self.order_queue = order_queue
        self.control_system = control_system
        
        # Internal state tracking (Replaces the shared TOrder._next_id)
        self.orders_generated: int = 0
        self.orders: list[Order] = []

    def process(self):
        """Main generator loop. (Salabim yieldless paradigm)."""
        while True:
            # 1. Sample inter-arrival time
            mean_iat = mean_iat_minutes(self.env.now())
            iat = sim.Exponential(mean_iat).sample()
            
            # Wait for the next arrival
            self.hold(iat)
            
            # 2. Generate the order
            self.orders_generated += 1
            item = random.choice(self.items)
            
            order = Order(
                order_id=self.orders_generated,
                item=item,
                arrival_min=self.env.now()
            )
            
            # 3. Store and emit
            self.orders.append(order)
            if self.order_queue is not None:
                self.order_queue.append(order)
                
            # Wake up the control system if it's waiting for orders
            if self.control_system and self.control_system.ispassive():
                self.control_system.activate()
