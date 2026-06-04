"""
Utility module for aggregating simulation metrics and KPIs.
"""

from datetime import datetime
from dataclasses import dataclass, field
import numpy as np

from src.utils.paths import LOGS_DIR

@dataclass
class SimulationMetrics:
    """Aggregates performance data for the final report."""
    warmup_min: float = 0.0
    sim_duration_min: float = 0.0
    total_orders_generated: int = 0
    total_orders_completed: int = 0
    pending_orders: int = 0
    in_progress_orders: int = 0
    energy_consumed_wh: float = 0.0
    order_fulfillment_times: list[float] = field(default_factory=list)
    agv_metrics: dict[int, dict] = field(default_factory=dict)
    
    # New KPIs
    total_mass_delivered: float = 0.0
    total_distance_traveled: float = 0.0
    peak_throughput_hr: float = 0.0
    min_fleet_soc: float = 100.0
    batching_delays: list[float] = field(default_factory=list)
    avg_packing_queue_min: float = 0.0
    total_stops: int = 0
    total_tasks_completed: int = 0

    def report(self, save_to_file=False):
        """Prints a structured summary of the simulation results and optionally saves to file."""
        lines = []
        lines.append("\n==================================================")
        lines.append("      SAS AGV SIMULATION SUMMARY REPORT")
        lines.append("==================================================")
        run_duration_hr = self.sim_duration_min / 60
        lines.append(f"Simulation Run Duration:   {self.sim_duration_min:.2f} min ({run_duration_hr:.0f}h)")
        lines.append(f"Warm-up Period Applied:    {self.warmup_min:.2f} min")
        lines.append("")
        
        lines.append("--- Order Lifecycle & Integrity ---")
        lines.append(f"Total Orders Generated:   {self.total_orders_generated}")
        lines.append(f"Total Orders Fulfilled:   {self.total_orders_completed}")
        lines.append(f"Orders Still Pending:     {self.pending_orders}")
        lines.append(f"Orders In Progress:       {self.in_progress_orders}")
        lines.append("")

        lines.append("--- Optimization Targets (Goal KPIs) ---")
        lines.append(f"Total Energy Consumed:    {self.energy_consumed_wh:.2f} Wh")
        
        efficiency = (self.energy_consumed_wh / self.total_orders_completed) if self.total_orders_completed > 0 else 0.0
        lines.append(f"Energy per Order:         {efficiency:.2f} Wh/order")
        
        spec_energy = (self.energy_consumed_wh / self.total_mass_delivered) if self.total_mass_delivered > 0 else 0.0
        lines.append(f"Specific Energy Exp:      {spec_energy:.2f} Wh/kg")
        
        avg_dist = (self.total_distance_traveled / self.total_orders_completed) if self.total_orders_completed > 0 else 0.0
        lines.append(f"Avg Distance per Order:   {avg_dist:.2f} m/order")
        lines.append("")
        
        lines.append("--- Service Level Objectives (Constraint KPIs) ---")
        avg_throughput = (self.total_orders_completed / run_duration_hr) if run_duration_hr > 0 else 0.0
        lines.append(f"Avg Throughput:           {avg_throughput:.2f} orders/hour")
        lines.append(f"Peak Hourly Throughput:   {self.peak_throughput_hr:.2f} orders/hour")
        
        if self.order_fulfillment_times:
            avg_time = np.mean(self.order_fulfillment_times)
            p95_time = np.percentile(self.order_fulfillment_times, 95)
            max_time = np.max(self.order_fulfillment_times)
            lines.append(f"Avg Cycle (Fulfill) Time: {avg_time:.2f} min")
            lines.append(f"95th Percentile Cycle:    {p95_time:.2f} min")
            lines.append(f"Max Cycle (Fulfill) Time: {max_time:.2f} min")
        else:
            lines.append("Avg Cycle (Fulfill) Time: 0.00 min")
            lines.append("95th Percentile Cycle:    0.00 min")
            lines.append("Max Cycle (Fulfill) Time: 0.00 min")
            
        lines.append(f"Min Fleet SoC Recorded:   {self.min_fleet_soc:.1f} %")
        lines.append("")
        
        lines.append("--- Diagnostic Metrics ---")
        avg_batch_delay = np.mean(self.batching_delays) if self.batching_delays else 0.0
        lines.append(f"Avg Batching Delay:       {avg_batch_delay:.2f} min")
        lines.append(f"Avg Packing Queue Time:   {self.avg_packing_queue_min:.2f} min")
        
        avg_stops = (self.total_stops / self.total_tasks_completed) if self.total_tasks_completed > 0 else 0.0
        lines.append(f"Avg Edges Traversed:      {avg_stops:.2f}")
        lines.append("")
        
        lines.append("--- AGV Fleet Breakdown ---")
        for agv_id, data in self.agv_metrics.items():
            lines.append(f"AGV {agv_id}: Energy={data['energy']:.1f} Wh, Tasks={data['tasks']}, Min SoC={data['min_soc']:.0f}%, Moving={data['moving_pct']:.0f}%, Idle={data['idle_pct']:.0f}%, Charging={data['charging_pct']:.0f}%")
        lines.append("==================================================\n")
        
        output = "\n".join(lines)
        print(output)
        
        if save_to_file:
            logfile = f"{LOGS_DIR}/summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(logfile, "w") as f:
                f.write(output)
