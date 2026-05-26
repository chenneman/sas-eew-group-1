"""
Task data model.
"""

from dataclasses import dataclass
from src.models.item import Item

@dataclass
class PickupSegment:
    """Represents a single leg of a pickup journey."""
    route: list[int]
    items: list[Item]
    pick_time: float

@dataclass
class Task:
    """
    Represents a movement and transport task assigned to an AGV, supporting multi-stop picking.
    """
    task_id: int
    pickups: list[PickupSegment]
    dropoff_route: list[int]
    
    @property
    def all_items(self) -> list[Item]:
        """Returns a flat list of all items across all pickups."""
        return [item for pickup in self.pickups for item in pickup.items]
