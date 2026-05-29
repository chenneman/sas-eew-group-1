"""
Visual test for warehouse_layout.py.

Run from the repository root:
    python visualise_layout.py   (or: uv run python visualise_layout.py)

Saves layout_test.png in the same directory as this script.
"""

import math
import pathlib
import random
import sys

# ── Ensure src.* imports resolve when called from any working directory ────────
_ROOT = pathlib.Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Headless backend — works without a display and produces a clean PNG
import matplotlib
matplotlib.use("Agg")

import matplotlib.collections as mc
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from src.models.graph import NodeType
from src.models.warehouse_layout import TWarehouseLayout

# ── Colour scheme ──────────────────────────────────────────────────────────────
COLOR = {
    NodeType.AISLE:    "#AAAAAA",   # grey
    NodeType.SHELF:    "#8B4513",   # brown
    NodeType.PACKING:  "#1565C0",   # blue
    NodeType.CHARGING: "#2E7D32",   # green
    NodeType.IDLE:     "#66BB6A",   # light-green
    NodeType.BORDER:   "#FFFFFF",   # white
}

# ── 1. Build layout ────────────────────────────────────────────────────────────
layout = TWarehouseLayout()
G      = layout.graph._graph   # the underlying networkx.Graph

# ── 2. Pre-compute per-node data ───────────────────────────────────────────────
id_to_xy: dict[int, tuple[int, int]] = {}
by_type:  dict[NodeType, list]       = {nt: [] for nt in NodeType}

for nid, data in G.nodes(data=True):
    xy = data["pos"]
    nt = data["type"]
    id_to_xy[nid] = xy
    by_type[nt].append(xy)

type_counts = {nt: len(coords) for nt, coords in by_type.items()}
total_nodes = G.number_of_nodes()
total_edges = G.number_of_edges()

# ── 3. Shortest path: random shelf node → nearest packing station ──────────────
random.seed(42)
src_node = random.choice(layout.shelf_nodes)

tgt_node = min(
    layout.packing_nodes,
    key=lambda n: math.dist(src_node.coords, n.coords),
)

path_ids = layout.graph.get_shortest_path(src_node.id, tgt_node.id)

# ── 4. Console summary ─────────────────────────────────────────────────────────
SEP = "=" * 54
print(SEP)
print("  WAREHOUSE LAYOUT VERIFICATION")
print(SEP)
print(f"  Total nodes       : {total_nodes}")
print(f"  Total edges       : {total_edges}")
print()
for nt in NodeType:
    print(f"  {nt.name:<10} : {type_counts[nt]}")
print()

ok_shelf = len(layout.shelf_nodes)   == 100
ok_pack  = len(layout.packing_nodes) == 2
ok_path  = path_ids is not None and len(path_ids) > 0

print(f"  [{'OK' if ok_shelf else 'FAIL'}] len(shelf_nodes) == 100          "
      f"(got {len(layout.shelf_nodes)})")
print(f"  [{'OK' if ok_pack  else 'FAIL'}] len(packing_nodes) == 2          "
      f"(got {len(layout.packing_nodes)})")
print(f"  [{'OK' if ok_path  else 'FAIL'}] path not None and len > 0        "
      f"(got {len(path_ids) if path_ids else 0})")
print()
print(f"  Source (shelf)    : node {src_node.id:>4}  at {src_node.coords}")
print(f"  Target (packing)  : node {tgt_node.id:>4}  at {tgt_node.coords}")
print(f"  Path length       : {len(path_ids)} steps")
print(SEP)

# ── 5. Drawing helpers ─────────────────────────────────────────────────────────

def _setup_ax(ax: plt.Axes, title: str) -> None:
    ax.set_xlim(-1, 28)
    ax.set_ylim(-1, 24)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)", fontsize=9)
    ax.set_ylabel("y (m)", fontsize=9)
    ax.set_xticks(range(0, 28, 2))
    ax.set_yticks(range(0, 24, 2))
    ax.tick_params(labelsize=7)
    ax.set_facecolor("#F5F5F5")
    ax.set_title(title, fontsize=10, pad=6)


def _draw_edges(ax: plt.Axes) -> None:
    segs = [[id_to_xy[u], id_to_xy[v]] for u, v in G.edges()]
    lc = mc.LineCollection(segs, colors="#CCCCCC", linewidths=0.3, zorder=1)
    ax.add_collection(lc)


def _draw_nodes(ax: plt.Axes) -> None:
    # Paint in increasing z-order so important nodes sit on top
    draw_order = [
        NodeType.BORDER,
        NodeType.AISLE,
        NodeType.SHELF,
        NodeType.IDLE,
        NodeType.CHARGING,
        NodeType.PACKING,
    ]
    for nt in draw_order:
        coords = by_type[nt]
        if not coords:
            continue
        xs, ys = zip(*coords)

        big   = nt in (NodeType.PACKING, NodeType.CHARGING, NodeType.IDLE)
        alpha = 0.30 if nt == NodeType.BORDER else 1.0
        ec    = "black"    if big                     else \
                "#BBBBBB"  if nt == NodeType.BORDER   else "none"
        lw    = 0.5        if big                     else \
                0.3        if nt == NodeType.BORDER   else 0.0
        size  = 30         if big                     else \
                12         if nt == NodeType.SHELF    else 8

        ax.scatter(xs, ys, s=size, c=COLOR[nt], alpha=alpha,
                   edgecolors=ec, linewidths=lw, zorder=2)


# ── 6. Build figure ────────────────────────────────────────────────────────────
fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(18, 8))
fig.suptitle("Warehouse Layout Visual Test  (28 × 24 m)", fontsize=13, y=1.00)

# Left panel — full layout
_draw_edges(ax_left)
_draw_nodes(ax_left)
_setup_ax(ax_left, f"Full layout  •  {total_nodes} nodes  •  {total_edges} edges")

# Right panel — same layout with path overlay
_draw_edges(ax_right)
_draw_nodes(ax_right)

path_x = [id_to_xy[n][0] for n in path_ids]
path_y = [id_to_xy[n][1] for n in path_ids]

ax_right.plot(path_x, path_y, "-", color="#D32F2F", linewidth=2.2, zorder=4)
ax_right.plot(path_x[0],  path_y[0],  "o",
              color="#D32F2F", markersize=8, zorder=5,
              label=f"source  node {src_node.id} {src_node.coords}")
ax_right.plot(path_x[-1], path_y[-1], "D",
              color="#1565C0", markersize=9, zorder=5,
              markeredgecolor="black", markeredgewidth=0.5,
              label=f"target  node {tgt_node.id} {tgt_node.coords}")
ax_right.legend(fontsize=8, loc="upper right", framealpha=0.85)

_setup_ax(
    ax_right,
    f"Shortest path  •  node {src_node.id} {src_node.coords}"
    f" → node {tgt_node.id} {tgt_node.coords}  "
    f"({len(path_ids)} steps)",
)

# Shared legend at the bottom
legend_handles = [
    mpatches.Patch(color=COLOR[NodeType.AISLE],
                   label=f"Aisle  ({type_counts[NodeType.AISLE]})"),
    mpatches.Patch(color=COLOR[NodeType.SHELF],
                   label=f"Shelf  ({type_counts[NodeType.SHELF]})"),
    mpatches.Patch(color=COLOR[NodeType.PACKING],
                   label=f"Packing  ({type_counts[NodeType.PACKING]})"),
    mpatches.Patch(color=COLOR[NodeType.CHARGING],
                   label=f"Charging  ({type_counts[NodeType.CHARGING]})"),
    mpatches.Patch(color=COLOR[NodeType.IDLE],
                   label=f"Idle  ({type_counts[NodeType.IDLE]})"),
    mpatches.Patch(facecolor=COLOR[NodeType.BORDER], edgecolor="#BBBBBB",
                   linewidth=0.5,
                   label=f"Border  ({type_counts[NodeType.BORDER]})"),
    mlines.Line2D([], [], color="#D32F2F", linewidth=2,
                  label="Shortest path"),
]
fig.legend(
    handles=legend_handles,
    loc="lower center",
    ncol=7,
    fontsize=9,
    bbox_to_anchor=(0.5, -0.02),
    framealpha=0.92,
)

plt.tight_layout(rect=[0, 0.05, 1, 1])

# ── 7. Save ────────────────────────────────────────────────────────────────────
out = _ROOT / "layout_test.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print(f"\nFigure saved → {out}")
