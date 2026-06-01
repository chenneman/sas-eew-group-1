"""
Graph models for representing the warehouse layout.

This module defines the NodeType enum, Node class, and RoutingGraph class
used to model the physical structure and connectivity of the warehouse
using networkx for optimized pathfinding.
"""

from enum import Enum
import math
import networkx as nx

class NodeType(Enum):
    """Enumeration of possible node types in the warehouse."""
    SHELF = 1
    PACKING = 2
    CHARGING = 3
    IDLE = 4
    AISLE = 5
    BORDER = 6


class Node:
    """
    Represents a single point in the warehouse graph.

    Attributes:
        id (int): Unique identifier for the node.
        coords (tuple[int, int]): (x, y) coordinates of the node.
        type (NodeType): The functional type of the node.
    """
    def __init__(self, node_id: int, coords: tuple[int, int], node_type: NodeType):
        self.id = node_id
        self.coords = coords
        self.type = node_type


class RoutingGraph:
    """
    Represents the warehouse layout, wrapping networkx for pathfinding.

    Nodes represent physical locations, and edges represent paths between them
    with distances calculated based on coordinates.
    """
    def __init__(self) -> None:
        """Initializes an empty networkx Graph."""
        self._graph = nx.Graph()

    def add_node(self, node: Node) -> None:
        """
        Adds a node to the graph.

        Args:
            node (Node): The node object to add.
        """
        self._graph.add_node(node.id, pos=node.coords, type=node.type)

    def add_edge(self, id_a: int, id_b: int) -> None:
        """
        Adds an undirected edge between two nodes.

        The distance is automatically calculated as the Euclidean distance
        between the nodes' coordinates.

        Args:
            id_a (int): ID of the first node.
            id_b (int): ID of the second node.
        """
        pos_a = self._graph.nodes[id_a]['pos']
        pos_b = self._graph.nodes[id_b]['pos']

        dist = math.dist(pos_a, pos_b)
        self._graph.add_edge(id_a, id_b, weight=dist)

    def get_shortest_path(self, start_id: int, end_id: int) -> list[int]:
        """
        Calculates the shortest path using A* search.

        Args:
            start_id (int): Starting node ID.
            end_id (int): Destination node ID.

        Returns:
            list[int]: A sequence of node IDs representing the optimal route.
        """
        return nx.astar_path(self._graph, start_id, end_id, weight='weight')

    def visualize(self) -> None:
        """Plots the warehouse layout using matplotlib."""
        import matplotlib.pyplot as plt

        pos = nx.get_node_attributes(self._graph, 'pos')
        nx.draw(
            self._graph, pos, with_labels=True,
            node_color='lightblue', font_weight='bold', node_size=500
        )
        plt.show()