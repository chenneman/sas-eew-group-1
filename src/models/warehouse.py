"""Static warehouse layout generator."""

from __future__ import annotations

import numpy as np
import salabim as sim

from src.config import L_WH, W_WH, N_SERVERS, N_CHARGERS
from src.models.graph import Node, NodeType, RoutingGraph


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
        n_shelf_nodes: int = 100,
        n_packing: int = N_SERVERS,
        n_chargers: int = N_CHARGERS,
    ) -> None:

        # ── Derive bay geometry ───────────────────────────────────────────────
        # Each bay: [left_shelf | aisle×aisle_width | right_shelf]  → 4 columns
        # Between bays: 1-column inter-bay corridor
        # Outer margins: (L - total_bay_cols) / 2 columns on each side
        n_bays = n_shelf_nodes // (2 * cross_aisle_spacing)  # e.g., 5
        shelf_rows = cross_aisle_spacing                     # e.g., 10
        bay_width = aisle_width + 2                          # e.g., 4
        total_bay_x = n_bays * bay_width + (n_bays - 1)      # e.g., 24
        margin = (length - total_bay_x) // 2                      # e.g., 2

        # Left-shelf x-coordinate for each bay: [2, 7, 12, 17, 22]
        bay_left_xs = [margin + i * (bay_width + 1) for i in range(n_bays)]

        shelf_x_set: set[int] = set()
        for lx in bay_left_xs:
            shelf_x_set.add(lx)                    # left shelf column
            shelf_x_set.add(lx + aisle_width + 1)  # right shelf column

        # Shelf y-range: centred in W → y = 7 … 16
        shelf_y_min = (width - shelf_rows) // 2
        shelf_y_max = shelf_y_min + shelf_rows - 1
        shelf_y_set = set(range(shelf_y_min, shelf_y_max + 1))

        # Packing stations: n_packing nodes evenly spaced at packing_y
        packing_y = shelf_y_min - 3   # 4
        packing_xs = [int(round(length * (i + 1) / (n_packing + 1)))
                      for i in range(n_packing)]   # [9, 19]
        packing_coord_set = {(x, packing_y) for x in packing_xs}

        # Charging stations: n_chargers nodes in the left half of the top zone
        charging_y = shelf_y_max + 4  # 20
        charge_xs = [int(round(x)) for x in
                     np.linspace(margin, length // 2 - margin, n_chargers)]   # [2,5,9,12]
        charging_coord_set = {(x, charging_y) for x in charge_xs}

        # Idle spots: n_chargers nodes in the right half of the top zone
        idle_xs = [int(round(x)) for x in
                   np.linspace(length // 2 + margin, length - margin - 1, n_chargers)]  # [16,19,22,25]
        idle_coord_set = {(x, charging_y) for x in idle_xs}

        # ── Build RoutingGraph ────────────────────────────────────────────────
        self.routing_graph = RoutingGraph()
        
        all_nodes: list[Node] = []
        coord_to_id: dict[tuple, int] = {}

        nid = 0
        for y in range(width):
            for x in range(length):
                coords = (x, y)
                ntype = Warehouse._classify(
                    coords, length, width,
                    shelf_x_set, shelf_y_set,
                    packing_coord_set, charging_coord_set, idle_coord_set,
                )
                node = Node(nid, coords, ntype)
                self.routing_graph.add_node(node)
                all_nodes.append(node)
                coord_to_id[coords] = nid
                nid += 1

        # Orthogonal edges only — Euclidean weight = 1.0 per adjacent step
        for y in range(width):
            for x in range(length):
                if x + 1 < length:
                    self.routing_graph.add_edge(coord_to_id[(x, y)], coord_to_id[(x + 1, y)])
                if y + 1 < width:
                    self.routing_graph.add_edge(coord_to_id[(x, y)], coord_to_id[(x, y + 1)])

        # ── Lookup attributes (spec) ──────────────────────────────────────────
        self.shelf_nodes = [n for n in all_nodes if n.type == NodeType.SHELF]
        self.packing_nodes = [n for n in all_nodes if n.type == NodeType.PACKING]
        self.charging_nodes = [n for n in all_nodes if n.type == NodeType.CHARGING]
        self.idle_nodes = [n for n in all_nodes if n.type == NodeType.IDLE]
        
        self.location_to_node_id = coord_to_id
        
        # Extracted lists of IDs for quick access
        self.shelf_node_ids = [n.id for n in self.shelf_nodes]
        self.idle_spot_node_ids = [n.id for n in self.idle_nodes]
        self.packing_station_node_ids = [n.id for n in self.packing_nodes]
        self.charging_station_node_ids = [n.id for n in self.charging_nodes]
        
        # Stateful Salabim Queues (populated later by build_queues)
        self.packing_queues: list[dict] = []
        self.charger_queues: list[dict] = []

    @staticmethod
    def _classify(
        coords: tuple[int, int],
        L: int,
        W: int,
        shelf_x_set: set[int],
        shelf_y_set: set[int],
        packing_set: set[tuple],
        charging_set: set[tuple],
        idle_set: set[tuple],
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
        if x == 0 or x == L - 1 or y == 0 or y == W - 1:
            return NodeType.BORDER
        return NodeType.AISLE

    def build_queues(self, env: sim.Environment):
        """Initializes salabim Queues for packing and charging stations.
        
        This separates the static geometric generation from the stateful
        simulation component initialization.
        """
        self.packing_queues = [
            {"id": i + 1, "node_id": n.id, "queue": sim.Queue(name=f"packing_{i + 1}_queue", env=env)}
            for i, n in enumerate(self.packing_nodes)
        ]
        
        self.charger_queues = [
            {"id": i + 1, "node_id": n.id, "queue": sim.Queue(name=f"charger_{i + 1}_queue", env=env)}
            for i, n in enumerate(self.charging_nodes)
        ]
        
        return self
