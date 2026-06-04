"""
Task data model.
"""

from dataclasses import dataclass, field
from typing import Any

from src.entities.item import Item

@dataclass
class PickupSegment:
    """Represents a single leg of a pickup journey."""
    route: list[int]
    items: list[Item]
    pick_time: float

@dataclass
class Task:
    """
    Represents a movement and transport task assigned to an AGV.
    Supports both segment-based routing (for simulation) and flat routing (from Gurobi).
    """
    task_id: int
    orders: list[Any] = field(default_factory=list)
    pickups: list[PickupSegment] = field(default_factory=list)
    dropoff_route: list[int] = field(default_factory=list)
    route: list[int] = field(default_factory=list)  # Flat route from Gurobi
    agv: Any = None
    creation_time: float = 0.0
    
    @property
    def all_items(self) -> list[Item]:
        """Returns a flat list of all items across all pickups or orders."""
        if self.pickups:
            return [item for pickup in self.pickups for item in pickup.items]
        return [order.item for order in self.orders]

    def __repr__(self) -> str:
        agv_id = getattr(self.agv, 'agv_id', 'None') if self.agv else 'None'
        order_ids = [o.order_id for o in self.orders] if self.orders else []
        return f"Task#{self.task_id:04d} agv={agv_id} orders={order_ids}"
