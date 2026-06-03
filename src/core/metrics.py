"""
Utility module for aggregating simulation metrics and KPIs.
"""

from dataclasses import dataclass, field
import numpy as np

@dataclass
class SimulationMetrics:
    """Aggregates performance data for the final report."""
    total_orders_completed: int = 0
    energy_consumed_wh: float = 0.0
    order_fulfillment_times: list[float] = field(default_factory=list)
    agv_metrics: dict[int, dict] = field(default_factory=dict)

    def report(self):
        """Prints a structured summary of the simulation results."""
        print("\n" + "="*50)
        print("      SAS AGV SIMULATION SUMMARY REPORT")
        print("="*50)
        print(f"Total Orders Fulfilled:    {self.total_orders_completed}")
        
        if self.order_fulfillment_times:
            avg_time = np.mean(self.order_fulfillment_times)
            max_time = np.max(self.order_fulfillment_times)
            print(f"Avg Fulfillment Time:     {avg_time:.2f} min")
            print(f"Max Fulfillment Time:     {max_time:.2f} min")
        
        print(f"Total Energy Consumed:    {self.energy_consumed_wh:.2f} Wh")
        
        if self.total_orders_completed > 0:
            efficiency = self.energy_consumed_wh / self.total_orders_completed
            print(f"Energy per Order:         {efficiency:.2f} Wh/order")
        
        print("\n--- AGV Fleet Breakdown ---")
        for agv_id, data in self.agv_metrics.items():
            print(f"AGV {agv_id}: Energy={data['energy']:.1f} Wh, Tasks={data['tasks']}")
        print("="*50 + "\n")
