#TODO replace with actual implementation

"""
Task data model.
"""

from dataclasses import dataclass

@dataclass
class Task:
    """
    Represents a movement and transport task assigned to an AGV.

    :param task_id: Unique identifier for the task.
    :type task_id: int
    :param item_weight: The physical weight of the item to be transported (in kg).
    :type item_weight: float
    :param pick_time: The time required to load the item onto the AGV (in seconds).
    :type pick_time: float
    :param pickup_route: A sequence of node IDs defining the path to the storage shelf.
    :type pickup_route: list[int]
    :param dropoff_route: A sequence of node IDs defining the path from the shelf to the packing area.
    :type dropoff_route: list[int]
    """
    task_id: int
    item_weight: float
    pick_time: float
    pickup_route: list[int]
    dropoff_route: list[int]