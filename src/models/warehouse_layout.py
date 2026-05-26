"""Static warehouse layout for the IKEA warehouse fulfilment DES."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import numpy as np
import pandas as pd
import salabim as sim
sim.yieldless(False)

from src.utils.paths import DATA_DIR, SELECTED_ITEMS_CSV

# ── Parameters ────────────────────────────────────────────────────────────────

GRID_SIZE      = 24            # metres (24 × 24 grid)
N_AGV          = 4
N_SERVERS      = 2
N_CHARGERS     = 4

Y_BOTTOM_TOP   = 7             # zone boundary: bottom strip / middle strip
Y_MIDDLE_TOP   = 17            # zone boundary: middle strip / top strip

N_BAYS         = 5
AISLE_X        = [4, 8, 12, 16, 20]    # aisle centre-line x-coords
SHELF_Y_MIN    = 8
SHELF_Y_MAX    = 17                     # inclusive → 10 nodes per side
NODES_PER_SIDE = SHELF_Y_MAX - SHELF_Y_MIN + 1

PACKING_LOCS   = [(8, 3), (16, 3)]

CHARGER_Y      = 20
CHARGER_LOCS   = [(int(round(x)), CHARGER_Y)
                  for x in np.linspace(1, 9, N_CHARGERS)]   # (1,20)(4,20)(6,20)(9,20)

IDLE_Y         = 20
IDLE_LOCS      = [(int(round(x)), IDLE_Y)
                  for x in np.linspace(15, 23, N_AGV)]       # (15,20)(18,20)(20,20)(23,20)

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
    """Passive container for all static warehouse entities."""

    def __init__(self) -> None:
        self.shelf_nodes:      dict[int, tuple[int, int]] = {}
        self.shelf_items:      dict[int, TItem]           = {}
        self.packing_stations: list[dict]                 = []
        self.charger_stations: list[dict]                 = []
        self.idle_spots:       list[tuple[int, int]]      = []
        self.routing_graph:    None                       = None  # populated in a later session

    def build(self, items: list[TItem], env: sim.Environment) -> "TWarehouseLayout":
        """Populate all layout collections.  Returns self for chaining."""
        self._build_shelf_nodes()
        self._assign_items(items)
        self._build_packing_stations(env)
        self._build_charger_stations(env)
        self._build_idle_spots()
        return self

    def _build_shelf_nodes(self) -> None:
        node_id = 0
        for aisle_x in AISLE_X:
            for shelf_x in (aisle_x - 1, aisle_x + 1):   # left shelf then right shelf
                for y in range(SHELF_Y_MIN, SHELF_Y_MAX + 1):
                    self.shelf_nodes[node_id] = (shelf_x, y)
                    node_id += 1

    def _assign_items(self, items: list[TItem]) -> None:
        for node_id, item in zip(self.shelf_nodes, items):
            loc = self.shelf_nodes[node_id]
            item.shelf_location = loc
            self.shelf_items[node_id] = item

    def _build_packing_stations(self, env: sim.Environment) -> None:
        for i, loc in enumerate(PACKING_LOCS, start=1):
            self.packing_stations.append({
                "id":       i,
                "location": loc,
                "queue":    sim.Queue(name=f"packing_{i}_queue", env=env),
            })

    def _build_charger_stations(self, env: sim.Environment) -> None:
        for i, loc in enumerate(CHARGER_LOCS, start=1):
            self.charger_stations.append({
                "id":       i,
                "location": loc,
                "queue":    sim.Queue(name=f"charger_{i}_queue", env=env),
            })

    def _build_idle_spots(self) -> None:
        self.idle_spots = list(IDLE_LOCS)

# ── load_items ────────────────────────────────────────────────────────────────

def load_items(csv_path: str | pathlib.Path = SELECTED_ITEMS_CSV) -> list[TItem]:
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
    items  = load_items(csv_path)
    layout = TWarehouseLayout().build(items, env)
    return layout

# ── Verification block ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    layout = build_warehouse()

    # ── Summary table ─────────────────────────────────────────────────────────
    print("=" * 55)
    print("  WAREHOUSE LAYOUT SUMMARY")
    print("=" * 55)
    print(f"  Grid               : {GRID_SIZE} × {GRID_SIZE} m")
    print(f"  Shelf nodes        : {len(layout.shelf_nodes)}")
    print(f"  Items on shelves   : {len(layout.shelf_items)}")
    print()
    print("  Packing stations")
    for ps in layout.packing_stations:
        print(f"    P{ps['id']}  at {ps['location']}")
    print()
    print("  Charger stations")
    for cs in layout.charger_stations:
        print(f"    C{cs['id']}  at {cs['location']}")
    print()
    print("  Idle spots")
    for i, loc in enumerate(layout.idle_spots, start=1):
        print(f"    I{i}  at {loc}")
    print("=" * 55)

    # First 5 shelf assignments as a sanity check
    print("\n  First 5 shelf assignments")
    print(f"  {'Node':>4}  {'(x,y)':>8}  {'TItem'}")
    print("  " + "-" * 40)
    for nid in range(5):
        item = layout.shelf_items.get(nid)
        print(f"  {nid:>4}  {str(layout.shelf_nodes[nid]):>8}  {item}")

    # ── Matplotlib top-down plot ───────────────────────────────────────────────
    BAY_COLORS = ["#4878d0", "#ee854a", "#6acc65", "#d65f5f", "#b47cc7"]

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.set_xlim(-0.5, GRID_SIZE - 0.5)
    ax.set_ylim(-0.5, GRID_SIZE - 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Warehouse Layout  (top-down, 24 × 24 m)")

    # Zone boundary lines
    for y_bound in (Y_BOTTOM_TOP, Y_MIDDLE_TOP):
        ax.axhline(y_bound, color="black", linestyle="--", linewidth=1.1, alpha=0.7,
                   zorder=2)

    # Zone labels (left margin)
    ax.text(0.2, 3.5,  "Packing / AGV buffer", fontsize=7, color="dimgrey", va="center")
    ax.text(0.2, 12.0, "Shelf picking zone",   fontsize=7, color="dimgrey", va="center")
    ax.text(0.2, 20.5, "Chargers / Idle",      fontsize=7, color="dimgrey", va="center")

    # Shelf nodes coloured by bay
    for b, bay_x in enumerate(AISLE_X):
        c = BAY_COLORS[b]
        for shelf_x in (bay_x - 1, bay_x + 1):
            ys = range(SHELF_Y_MIN, SHELF_Y_MAX + 1)
            ax.plot([shelf_x] * len(ys), list(ys), "s",
                    color=c, markersize=6, zorder=3)

    # Aisle centre-line guides (faint vertical)
    for bay_x in AISLE_X:
        ax.axvline(bay_x, color="lightgrey", linestyle=":", linewidth=0.8, zorder=1)

    # Packing stations
    for ps in layout.packing_stations:
        x, y = ps["location"]
        ax.plot(x, y, "D", color="crimson", markersize=9, zorder=5)
        ax.text(x, y + 0.45, f"P{ps['id']}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="crimson")

    # Charger stations
    for cs in layout.charger_stations:
        x, y = cs["location"]
        ax.plot(x, y, "^", color="#c8960c", markersize=9, zorder=5)
        ax.text(x, y + 0.45, f"C{cs['id']}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="#c8960c")

    # Idle spots
    for i, (x, y) in enumerate(layout.idle_spots, start=1):
        ax.plot(x, y, "o", color="steelblue", markersize=9, zorder=5)
        ax.text(x, y + 0.45, f"I{i}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="steelblue")

    # Legend
    legend_elements = [
        mpatches.Patch(color=BAY_COLORS[b],
                       label=f"Bay {b + 1}  (aisle x={AISLE_X[b]})")
        for b in range(N_BAYS)
    ] + [
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="crimson",
                   markersize=8, label="Packing station"),
        plt.Line2D([0], [0], marker="^", color="w", markerfacecolor="#c8960c",
                   markersize=8, label="Charger"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="steelblue",
                   markersize=8, label="Idle spot"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=7, framealpha=0.85)

    ax.set_xticks(range(GRID_SIZE))
    ax.set_yticks(range(GRID_SIZE))
    ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.5)
    plt.tight_layout()

    out = DATA_DIR / "warehouse_layout.png"
    plt.savefig(out, dpi=130)
    print(f"\nLayout plot saved → {out}")
