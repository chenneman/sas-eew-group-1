"""Static warehouse layout for the IKEA warehouse fulfilment DES."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import numpy as np
import pandas as pd
import salabim as sim
sim.yieldless(False)

from src.models.graph import Node, NodeType, RoutingGraph
from src.utils.paths import DATA_DIR, SELECTED_ITEMS_CSV

# ── Module-level parameters ───────────────────────────────────────────────────

L          = 28            # grid length in x (metres)
W          = 24            # grid width  in y (metres)
N_AGV      = 4
N_SERVERS  = 2
N_CHARGERS = N_AGV

# Backward-compat aliases (imported by test_smoke_run.py)
GRID_SIZE    = W           # kept for old visualization code
Y_BOTTOM_TOP = 7           # = shelf_y_min
Y_MIDDLE_TOP = 17          # = shelf_y_max + 1

# ── TItem ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=False)
class TItem:
    id:             int
    sku:            int
    mass_kg:        float
    volume_m3:      float
    shelf_location: tuple[int, int] | None = None
    status:         str                    = "ON_SHELF"
    parentOrder:    object                 = None

    def __repr__(self) -> str:
        return (f"TItem#{self.id:04d}  sku={self.sku}"
                f"  loc={self.shelf_location}  status={self.status}")

# ── TWarehouseLayout ──────────────────────────────────────────────────────────

class TWarehouseLayout:
    """Warehouse layout built on top of RoutingGraph.

    __init__ constructs the full routing graph (pure geometry, no salabim).
    build()   assigns TItem objects to shelf nodes and creates sim.Queue objects.
    """

    def __init__(
        self,
        L: int = 28,
        W: int = 24,
        aisle_width: int = 2,
        cross_aisle_spacing: int = 10,
        n_shelf_nodes: int = 100,
        n_packing: int = 2,
        n_chargers: int = N_AGV,
    ) -> None:

        # ── Derive bay geometry ───────────────────────────────────────────────
        # Each bay: [left_shelf | aisle×aisle_width | right_shelf]  → 4 columns
        # Between bays: 1-column inter-bay corridor
        # Outer margins: (L - total_bay_cols) / 2 columns on each side
        n_bays     = n_shelf_nodes // (2 * cross_aisle_spacing)  # 5
        shelf_rows = cross_aisle_spacing                          # 10
        bay_width  = aisle_width + 2                              # 4
        total_bay_x = n_bays * bay_width + (n_bays - 1)          # 24
        margin      = (L - total_bay_x) // 2                     # 2

        # Left-shelf x-coordinate for each bay: [2, 7, 12, 17, 22]
        bay_left_xs = [margin + i * (bay_width + 1) for i in range(n_bays)]

        shelf_x_set: set[int] = set()
        for lx in bay_left_xs:
            shelf_x_set.add(lx)                    # left shelf column
            shelf_x_set.add(lx + aisle_width + 1)  # right shelf column

        # Shelf y-range: centred in W → y = 7 … 16
        shelf_y_min = (W - shelf_rows) // 2
        shelf_y_max = shelf_y_min + shelf_rows - 1
        shelf_y_set = set(range(shelf_y_min, shelf_y_max + 1))

        # Packing stations: n_packing nodes evenly spaced at packing_y
        packing_y         = shelf_y_min - 3   # 4
        packing_xs        = [int(round(L * (i + 1) / (n_packing + 1)))
                             for i in range(n_packing)]   # [9, 19]
        packing_coord_set = {(x, packing_y) for x in packing_xs}

        # Charging stations: n_chargers nodes in the left half of the top zone
        charging_y         = shelf_y_max + 4  # 20
        charge_xs          = [int(round(x)) for x in
                              np.linspace(margin, L // 2 - margin, n_chargers)]   # [2,5,9,12]
        charging_coord_set = {(x, charging_y) for x in charge_xs}

        # Idle spots: n_chargers nodes in the right half of the top zone
        idle_xs      = [int(round(x)) for x in
                        np.linspace(L // 2 + margin, L - margin - 1, n_chargers)]  # [16,19,22,25]
        idle_coord_set = {(x, charging_y) for x in idle_xs}

        # ── Build RoutingGraph ────────────────────────────────────────────────
        self.graph         = RoutingGraph()
        self.routing_graph = self.graph   # alias used by charger.py / controlsystem.py

        all_nodes:   list[Node]         = []
        coord_to_id: dict[tuple, int]   = {}

        nid = 0
        for y in range(W):
            for x in range(L):
                coords = (x, y)
                ntype  = TWarehouseLayout._classify(
                    coords, L, W,
                    shelf_x_set, shelf_y_set,
                    packing_coord_set, charging_coord_set, idle_coord_set,
                )
                node = Node(nid, coords, ntype)
                self.graph.add_node(node)
                all_nodes.append(node)
                coord_to_id[coords] = nid
                nid += 1

        # Orthogonal edges only — Euclidean weight = 1.0 per adjacent step
        for y in range(W):
            for x in range(L):
                if x + 1 < L:
                    self.graph.add_edge(coord_to_id[(x, y)], coord_to_id[(x + 1, y)])
                if y + 1 < W:
                    self.graph.add_edge(coord_to_id[(x, y)], coord_to_id[(x, y + 1)])

        # ── Lookup attributes (spec) ──────────────────────────────────────────
        self.shelf_nodes    = [n for n in all_nodes if n.type == NodeType.SHELF]
        self.packing_nodes  = [n for n in all_nodes if n.type == NodeType.PACKING]
        self.charging_nodes = [n for n in all_nodes
                               if n.type in (NodeType.CHARGING, NodeType.IDLE)]

        # ── Attributes used by controlsystem.py / charger.py ─────────────────
        self.location_to_node_id      = coord_to_id
        self.idle_spot_node_ids       = [n.id for n in all_nodes if n.type == NodeType.IDLE]
        self.packing_station_node_ids = [n.id for n in self.packing_nodes]

        # ── Backward-compat attributes (test_smoke_run.py) ───────────────────
        self.idle_spots: list[tuple[int, int]] = [
            n.coords for n in all_nodes if n.type == NodeType.IDLE
        ]

        # Populated by build():
        self.shelf_items:      dict[int, TItem] = {}
        self.packing_stations: list[dict]       = []
        self.charger_stations: list[dict]       = []

    # ── Node type classifier ──────────────────────────────────────────────────

    @staticmethod
    def _classify(
        coords:        tuple[int, int],
        L:             int,
        W:             int,
        shelf_x_set:   set[int],
        shelf_y_set:   set[int],
        packing_set:   set[tuple],
        charging_set:  set[tuple],
        idle_set:      set[tuple],
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

    # ── Simulation entity setup ───────────────────────────────────────────────

    def build(self, items: list[TItem], env: sim.Environment) -> "TWarehouseLayout":
        """Assign TItems to shelf nodes and create salabim Queue objects."""
        for node, item in zip(self.shelf_nodes, items):
            item.shelf_location = node.coords
            self.shelf_items[node.id] = item

        self.packing_stations = [
            {
                "id":       i + 1,
                "location": n.coords,
                "queue":    sim.Queue(name=f"packing_{i + 1}_queue", env=env),
            }
            for i, n in enumerate(self.packing_nodes)
        ]

        charger_nodes = [n for n in self.charging_nodes if n.type == NodeType.CHARGING]
        self.charger_stations = [
            {
                "id":       i + 1,
                "location": n.coords,
                "queue":    sim.Queue(name=f"charger_{i + 1}_queue", env=env),
            }
            for i, n in enumerate(charger_nodes)
        ]

        return self


# ── _load_titems ──────────────────────────────────────────────────────────────

def _load_titems(csv_path: str | pathlib.Path = SELECTED_ITEMS_CSV) -> list[TItem]:
    """Read selected_simulation_items.csv and return one TItem per row."""
    path = pathlib.Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Items CSV not found: {path.absolute()}")

    df = pd.read_csv(path)
    df["SKU"] = df["SKU"].astype(int)

    items = []
    for idx, row in enumerate(df.itertuples(index=False), start=1):
        items.append(TItem(
            id=idx,
            sku=int(row.SKU),
            mass_kg=float(row.Weight),
            volume_m3=float(row.Volume_cm3) / 1_000_000,
        ))
    return items


# ── build_warehouse ───────────────────────────────────────────────────────────

def build_warehouse(
    csv_path: str | pathlib.Path = SELECTED_ITEMS_CSV,
    env: sim.Environment | None = None,
) -> TWarehouseLayout:
    """Construct and return a fully populated TWarehouseLayout."""
    if env is None:
        env = sim.Environment(trace=False)
    items  = _load_titems(csv_path)
    layout = TWarehouseLayout(n_chargers=N_CHARGERS).build(items, env)
    return layout


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    layout = TWarehouseLayout()

    n_nodes = layout.graph._graph.number_of_nodes()
    n_edges = layout.graph._graph.number_of_edges()

    print(f"Grid              : {L} × {W} m")
    print(f"Total nodes       : {n_nodes}")
    print(f"Total edges       : {n_edges}")
    print(f"Shelf nodes       : {len(layout.shelf_nodes)}")
    print(f"Packing nodes     : {len(layout.packing_nodes)}")
    print(f"Charging/idle nodes: {len(layout.charging_nodes)}")
    print()

    assert len(layout.shelf_nodes)   == 100, \
        f"Expected 100 shelf nodes, got {len(layout.shelf_nodes)}"
    assert len(layout.packing_nodes) == 2, \
        f"Expected 2 packing nodes, got {len(layout.packing_nodes)}"

    print("All assertions passed.")
