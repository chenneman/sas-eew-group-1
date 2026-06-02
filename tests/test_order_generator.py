"""
Validation and visual test for the OrderGenerator component.

Saves order_generator_validation.png in the logs directory.
"""

import statistics
import random
import numpy as np
import matplotlib.pyplot as plt
import salabim as sim

import matplotlib
matplotlib.use("Agg")

from src.utils.paths import LOGS_DIR
from src.config import ORDERS_PER_HOUR, TOTAL_MIN, WARMUP_MIN, SIM_START_HOUR, N_REPS
from src.entities.order import Order
from src.components.order_generator import OrderGenerator
from src.entities.item import load_items

# ── Replication runner ────────────────────────────────────────────────────────

def run_replication(seed: int, items: list) -> dict:
    """Run a single replication and return per-hour counts and order list."""
    random.seed(seed)
    
    # Use standard sim environment (yieldless mode by default)
    env = sim.Environment(trace=False, random_seed=seed)
    gen = OrderGenerator(env=env, items=items, name="OrderGenerator")
    
    env.run(till=TOTAL_MIN)

    hourly: list[int] = [0] * 24
    obs_orders: list[Order] = []
    
    # Calculate stats post-warmup
    for o in gen.orders:
        if o.arrival_min >= WARMUP_MIN:
            real_hour = int(SIM_START_HOUR + o.arrival_min // 60) % 24
            hourly[real_hour] += 1
            obs_orders.append(o)

    return {"total": len(obs_orders), "hourly": hourly, "orders": obs_orders}

# ── Validation block ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    THEORY_TOTAL = sum(ORDERS_PER_HOUR)
    
    # Load items just to populate the generator
    items = load_items()
    
    # --- 10-replication run ---------------------------------------------------
    results = []
    print(f"{'Rep':>4}  {'Total':>6}  First 6 timestamps")
    print("-" * 60)
    for rep in range(1, N_REPS + 1):
        r = run_replication(seed=rep * 42, items=items)
        results.append(r)
        sample = "  ".join(o.timestamp for o in r["orders"][:6])
        print(f"  {rep:2d}   {r['total']:5d}   {sample}")

    obs_counts = [r["total"] for r in results]
    mean_obs   = statistics.mean(obs_counts)
    stdev_obs  = statistics.stdev(obs_counts)
    ci_half    = 1.96 * stdev_obs / N_REPS ** 0.5

    print("-" * 60)
    print(f"\nMean generated orders        : {mean_obs:.1f}")
    print(f"Theoretical expected (Fig 5.2): {THEORY_TOTAL:.1f}")
    print(f"Relative error               : {abs(mean_obs - THEORY_TOTAL) / THEORY_TOTAL * 100:.1f}%")
    print(f"95% CI half-width            : ±{ci_half:.1f}")

    # --- Bar chart: simulated vs expected per hour ----------------------------
    hourly_matrix = np.array([r["hourly"] for r in results], dtype=float)
    h_mean = hourly_matrix.mean(axis=0)
    h_std  = hourly_matrix.std(axis=0, ddof=1)
    ci95   = 1.96 * h_std / np.sqrt(N_REPS)
    theory = np.array(ORDERS_PER_HOUR)
    hours  = np.arange(24)

    fig, ax = plt.subplots(figsize=(13, 4))
    w = 0.38
    ax.bar(hours - w / 2, h_mean, w, label="Simulated mean ± 95% CI",
           color="#1f4e79", alpha=0.85)
    ax.bar(hours + w / 2, theory, w, label="Figure 5.2 (target)",
           color="#2e75b6", alpha=0.50)
    ax.errorbar(hours - w / 2, h_mean, yerr=ci95,
                fmt="none", color="black", capsize=3, linewidth=1.1)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}:00" for h in hours],
                       rotation=45, ha="right", fontsize=7.5)
    ax.set_xlabel("Hour of the day")
    ax.set_ylabel("Number of orders")
    ax.set_title("Simulated vs Expected orders per hour  (10 replications)")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()

    out = LOGS_DIR / "order_generator_validation.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=120)
    print(f"\nChart saved → {out}")

    # --- Example order list: first 20 orders of replication 1 ----------------
    print(f"\n{'#Order ID':>9}  {'Timestamp':>10}    {'Status'}    {'Item ID'}")
    print("-" * 42)
    for o in results[0]["orders"][:20]:
        print(f"  {o.order_id:04d}       {o.timestamp}    {o.status.value}    {o.item.sku}")
