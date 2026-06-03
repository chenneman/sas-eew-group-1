"""Static warehouse layout generator."""

from __future__ import annotations

import numpy as np
import salabim as sim

from src.config import L_WH, W_WH, N_SERVERS, N_CHARGERS, N_ITEMS
from src.environment.graph import Node, NodeType, RoutingGraph
from src.utils.animation import grid_to_pixel, ANIMATION_SCALE


class Warehouse:
    """Warehouse layout built on top of RoutingGraph.
    
    This is a pure environment generator. It defines the physical nodes
    (shelves, aisles, packing stations, chargers, idle spots) and their connectivity.
    It does NOT manage inventory or Items.
    """

    def __init__(
            self,
            length: int = L_WH,
            width: int = W_WH,
            aisle_width: int = 2,
            cross_aisle_spacing: int = 10,
            n_shelf_nodes: int = N_ITEMS,
            n_packing: int = N_SERVERS,
            n_chargers: int = N_CHARGERS,
    ) -> None:

        # 1. Generate geometry sets
        (
            shelf_x_set, shelf_y_set,
            packing_coord_set, charging_coord_set, idle_coord_set
        ) = self._generate_geometry(
            length, width, aisle_width, cross_aisle_spacing,
            n_shelf_nodes, n_packing, n_chargers
        )

        # 2. Build RoutingGraph
        self.routing_graph = RoutingGraph()
        self.all_nodes, self.location_to_node_id = self._build_graph(
            length, width,
            shelf_x_set, shelf_y_set,
            packing_coord_set, charging_coord_set, idle_coord_set
        )

        # 3. Lookup attributes
        self.shelf_nodes = [n for n in self.all_nodes if n.type == NodeType.SHELF]
        self.packing_nodes = [n for n in self.all_nodes if n.type == NodeType.PACKING]
        self.charging_nodes = [n for n in self.all_nodes if n.type == NodeType.CHARGING]
        self.idle_nodes = [n for n in self.all_nodes if n.type == NodeType.IDLE]

        # Extracted lists of IDs for quick access
        self.shelf_node_ids = [n.id for n in self.shelf_nodes]
        self.idle_spot_node_ids = [n.id for n in self.idle_nodes]
        self.packing_station_node_ids = [n.id for n in self.packing_nodes]
        self.charging_station_node_ids = [n.id for n in self.charging_nodes]

        # Stateful Salabim Queues (populated later by build_queues)
        self.packing_queues: list[dict] = []
        self.charger_queues: list[dict] = []

        self._animate_layout()

    def _animate_layout(self):
        """Draws the static grid and functional zones using sim.AnimateRectangle."""
        
        for node in self.all_nodes:
            x_raw, y_raw = node.coords
            
            # Calculate pixel bounds
            x0 = x_raw * ANIMATION_SCALE
            y0 = y_raw * ANIMATION_SCALE
            x1 = x0 + ANIMATION_SCALE
            y1 = y0 + ANIMATION_SCALE
            
            # Determine color based on node type
            if node.type == NodeType.SHELF:
                color = "saddlebrown"
            elif node.type == NodeType.PACKING:
                color = "blue"
            elif node.type == NodeType.CHARGING:
                color = "green"
            elif node.type == NodeType.IDLE:
                color = "gray"
            else:
                color = "white"
                
            # Draw the cell
            sim.AnimateRectangle(
                spec=(x0, y0, x1, y1),
                fillcolor=color,
                linecolor="black",
                linewidth=1
            )

    def _generate_geometry(
            self,
            length: int, width: int, aisle_width: int, cross_aisle_spacing: int,
            n_shelf_nodes: int, n_packing: int, n_chargers: int
    ) -> tuple[
        set[int], set[int], set[tuple[int, int]], set[tuple[int, int]], set[tuple[int, int]]]:
        """Calculates coordinate sets for the different functional zones of the warehouse."""
        # ── Derive bay geometry ───────────────────────────────────────────────
        n_bays = n_shelf_nodes // (2 * cross_aisle_spacing)
        shelf_rows = cross_aisle_spacing
        bay_width = aisle_width + 2
        total_bay_x = n_bays * bay_width + (n_bays - 1)
        margin = (length - total_bay_x) // 2

        bay_left_xs = [margin + i * (bay_width + 1) for i in range(n_bays)]
        shelf_x_set: set[int] = set()
        for lx in bay_left_xs:
            shelf_x_set.add(lx)
            shelf_x_set.add(lx + aisle_width + 1)

        shelf_y_min = (width - shelf_rows) // 2
        shelf_y_max = shelf_y_min + shelf_rows - 1
        shelf_y_set = set(range(shelf_y_min, shelf_y_max + 1))

        packing_y = shelf_y_min - 3
        packing_xs = [int(round(length * (i + 1) / (n_packing + 1))) for i in range(n_packing)]
        packing_coord_set = {(x, packing_y) for x in packing_xs}

        charging_y = shelf_y_max + 4
        charge_xs = [int(round(x)) for x in np.linspace(margin, length // 2 - margin, n_chargers)]
        charging_coord_set = {(x, charging_y) for x in charge_xs}

        idle_xs = [int(round(x)) for x in
                   np.linspace(length // 2 + margin, length - margin - 1, n_chargers)]
        idle_coord_set = {(x, charging_y) for x in idle_xs}

        return shelf_x_set, shelf_y_set, packing_coord_set, charging_coord_set, idle_coord_set

    def _build_graph(
            self, length: int, width: int,
            shelf_x_set: set[int], shelf_y_set: set[int],
            packing_coord_set: set[tuple[int, int]],
            charging_coord_set: set[tuple[int, int]],
            idle_coord_set: set[tuple[int, int]]
    ) -> tuple[list[Node], dict[tuple[int, int], int]]:
        """Instantiates all nodes, assigns their NodeType, and builds the network edges."""
        all_nodes: list[Node] = []
        coord_to_id: dict[tuple[int, int], int] = {}

        nid = 0
        for y in range(width):
            for x in range(length):
                coords = (x, y)
                ntype = self._classify(
                    coords, length, width,
                    shelf_x_set, shelf_y_set,
                    packing_coord_set, charging_coord_set, idle_coord_set,
                )
                node = Node(nid, coords, ntype)
                self.routing_graph.add_node(node)
                all_nodes.append(node)
                coord_to_id[coords] = nid
                nid += 1

        for y in range(width):
            for x in range(length):
                if x + 1 < length:
                    self.routing_graph.add_edge(coord_to_id[(x, y)], coord_to_id[(x + 1, y)])
                if y + 1 < width:
                    self.routing_graph.add_edge(coord_to_id[(x, y)], coord_to_id[(x, y + 1)])

        return all_nodes, coord_to_id

    @staticmethod
    def _classify(
            coords: tuple[int, int],
            length: int,
            width: int,
            shelf_x_set: set[int],
            shelf_y_set: set[int],
            packing_set: set[tuple[int, int]],
            charging_set: set[tuple[int, int]],
            idle_set: set[tuple[int, int]],
    ) -> NodeType:
        if coords in packing_set:
            return NodeType.PACKING
        if coords in charging_set:
            return NodeType.CHARGING
        if coords in idle_set:
            return NodeType.IDLE
        x, y = coords
        if x in shelf_x_set and y in shelf_y_set:
            return NodeType.SHELF
        if x == 0 or x == length - 1 or y == 0 or y == width - 1:
            return NodeType.BORDER
        return NodeType.AISLE

    def build_queues(self, env: sim.Environment):
        """Initializes salabim Queues for packing and charging stations.
        
        This separates the static geometric generation from the stateful
        simulation component initialization.
        """
        self.packing_queues = [
            {"id": i + 1, "node_id": n.id,
             "queue": sim.Queue(name=f"packing_{i + 1}_queue", env=env)}
            for i, n in enumerate(self.packing_nodes)
        ]

        self.charger_queues = [
            {"id": i + 1, "node_id": n.id,
             "queue": sim.Queue(name=f"charger_{i + 1}_queue", env=env)}
            for i, n in enumerate(self.charging_nodes)
        ]

        return self
