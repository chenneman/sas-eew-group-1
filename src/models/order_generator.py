"""Order arrival generator for the warehouse fulfilment DES."""

import random
import statistics

import salabim as sim
sim.yieldless(False)

from src.models.item import load_items

# ── Parameters ───────────────────────────────────────────────────────────────

ORDERS_PER_HOUR = [
    13.0,  7.5,  5.0,  4.5,  4.0,  4.0,   # 00-05
     5.0,  8.0, 16.0, 24.0, 30.0, 32.0,   # 06-11
    29.5, 32.0, 32.0, 32.0, 32.5, 30.0,   # 12-17
    28.0, 30.0, 30.5, 30.5, 28.0, 21.0,   # 18-23
]
assert len(ORDERS_PER_HOUR) == 24

ITEMS = [item.sku for item in load_items()]

SIM_START_HOUR = 0
WARMUP_MIN     = 30
HORIZON_MIN    = 24 * 60
TOTAL_MIN      = WARMUP_MIN + HORIZON_MIN
N_REPS         = 10

# ── Helper functions ──────────────────────────────────────────────────────────

def sim_time_to_wallclock(sim_minute: float) -> str:
    total_seconds = int(sim_minute * 60)
    h = (SIM_START_HOUR + total_seconds // 3600) % 24
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def mean_iat_minutes(sim_minute: float) -> float:
    """Mean inter-arrival time [min] for the current simulation time."""
    real_hour = int(SIM_START_HOUR + sim_minute // 60) % 24
    lam = ORDERS_PER_HOUR[real_hour]
    return 60.0 / lam if lam > 0 else 60.0

# ── TOrder ────────────────────────────────────────────────────────────────────

class TOrder:
    _next_id = 1

    def __init__(self, arrival_sim_min: float, item):
        self.order_id    = TOrder._next_id
        TOrder._next_id += 1
        self.arrival_min = arrival_sim_min
        self.timestamp   = sim_time_to_wallclock(arrival_sim_min)
        self.status      = "PENDING"
        self.item        = item

    def __repr__(self):
        return (f"Order#{self.order_id:04d}  ts={self.timestamp}"
                f"  status={self.status}  item={self.item}")

# ── TOrderGenerator ───────────────────────────────────────────────────────────

class TOrderGenerator(sim.Component):
    """Salabim component that generates orders according to ORDERS_PER_HOUR rates.

    Parameters
    ----------
    env:
        The salabim Environment driving the simulation.
    items:
        Sequence of item IDs to sample from for each order.
    order_queue:
        Optional external list/queue; each new TOrder is appended to it
        in addition to self.orders (used to feed the ControlSystem).
    """

    def __init__(self, env: sim.Environment, items, order_queue=None, **kwargs):
        super().__init__(env=env, **kwargs)
        self.env         = env
        self.items       = items
        self.order_queue = order_queue
        self.orders: list[TOrder] = []

    def process(self):
        while True:
            mean_iat = mean_iat_minutes(self.env.now())
            iat = sim.Exponential(mean_iat).sample()
            yield self.hold(iat)
            item  = random.choice(self.items)
            order = TOrder(arrival_sim_min=self.env.now(), item=item)
            self.orders.append(order)
            if self.order_queue is not None:
                self.order_queue.append(order)

# ── Replication runner ────────────────────────────────────────────────────────

def run_replication(seed: int) -> dict:
    """Run a single replication and return per-hour counts and order list."""
    TOrder._next_id = 1
    random.seed(seed)

    env = sim.Environment(trace=False, random_seed=seed)
    gen = TOrderGenerator(env=env, items=ITEMS, name="OrderGenerator")
    env.run(till=TOTAL_MIN)

    hourly: list[int] = [0] * 24
    obs_orders: list[TOrder] = []
    for o in gen.orders:
        if o.arrival_min >= WARMUP_MIN:
            real_hour = int(SIM_START_HOUR + o.arrival_min // 60) % 24
            hourly[real_hour] += 1
            obs_orders.append(o)

    return {"total": len(obs_orders), "hourly": hourly, "orders": obs_orders}

# ── Validation block ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pathlib
    import numpy as np
    import matplotlib.pyplot as plt

    THEORY_TOTAL = sum(ORDERS_PER_HOUR)

    # --- 10-replication run ---------------------------------------------------
    results = []
    print(f"{'Rep':>4}  {'Total':>6}  First 6 timestamps")
    print("-" * 60)
    for rep in range(1, N_REPS + 1):
        r = run_replication(seed=rep * 42)
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

    out = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "order_generator_validation.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=120)
    print(f"\nChart saved → {out}")

    # --- Example order list: first 20 orders of replication 1 ----------------
    print(f"\n{'#Order ID':>9}  {'Timestamp':>10}    {'Status'}    {'Item ID'}")
    print("-" * 42)
    for o in results[0]["orders"][:20]:
        print(f"  {o.order_id:04d}       {o.timestamp}    {o.status}    {o.item}")
