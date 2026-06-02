"""Order data model."""

from enum import Enum
from dataclasses import dataclass
from entities.item import Item
from src.config import SIM_START_HOUR

class OrderStatus(Enum):
    """Lifecycle states of a customer order."""
    PENDING = "PENDING"     # Waiting in the central queue
    ASSIGNED = "ASSIGNED"   # Routed and assigned to a specific AGV
    COMPLETED = "COMPLETED" # Picked, delivered, and packed by the server

@dataclass
class Order:
    """
    Represents a logical customer request for a single item.
    
    This is a pure data structure. It does not generate its own ID; 
    the ID is provided by the OrderGenerator component.
    """
    order_id: int
    item: Item
    arrival_min: float
    status: OrderStatus = OrderStatus.PENDING
    completion_min: float | None = None

    @property
    def timestamp(self) -> str:
        """Computes a human-readable clock time string (HH:MM:SS) from the arrival minute."""
        total_seconds = int(self.arrival_min * 60)
        h = (SIM_START_HOUR + total_seconds // 3600) % 24
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def __repr__(self) -> str:
        return (f"Order#{self.order_id:04d}  ts={self.timestamp}"
                f"  status={self.status.value}  item={self.item.sku}")
