"""Charging-station component for AGVs."""

import salabim as sim
import logging

from src.components.agv import AGVStatus
from src.config import CHARGE_RATE, MAX_BATTERY

logger = logging.getLogger(__name__)


class Charger(sim.Component):
    """Charges AGVs and releases the fullest AGV first when multiple are waiting."""

    def setup(
        self,
        charger_id: int,
        queue: sim.Queue,
        charging_rate: float = CHARGE_RATE,
        location=None,
    ) -> None:
        self.charger_id = charger_id
        self.queue = queue
        self.charging_rate = charging_rate
        self.location = location
        
        # State machine variables
        self.state = "IDLE"
        self.current_agv = None

    def process(self):
        # Pure Yieldless State Machine
        while True:
            if self.state == "IDLE":
                if len(self.queue) == 0:
                    self.passivate()
                    continue
                    
                # Start serving the AGV with the highest battery percentage
                self.current_agv = self.best_charged_agv()
                self.current_agv.leave(self.queue)
                self.current_agv.status = AGVStatus.CHARGING
                
                logger.debug(f"[Charger {self.charger_id}] Starting charge for AGV {self.current_agv.agv_id} ({self.current_agv.soc:.1f}%)")
                
                charging_time = self.time_to_full(self.current_agv)
                
                if charging_time > 0:
                    self.state = "CHARGING"
                    self.hold(charging_time, mode="CHARGING")
                    continue
                else:
                    self.state = "FINISHING"
                    self.hold(0)
                    continue
                    
            elif self.state == "CHARGING" or self.state == "FINISHING":
                # Charging complete. 
                logger.info(f"[Charger {self.charger_id}] Finished charging AGV {self.current_agv.agv_id if self.current_agv else 'unknown'}")
                # The AGV should be full. Ensure it's full.
                self.current_agv.battery = MAX_BATTERY
                self.current_agv.status = AGVStatus.IDLE
                
                self.current_agv.activate()
                
                self.current_agv = None
                self.state = "IDLE"
                
                self.hold(0)
                continue

    def best_charged_agv(self):
        """Select the AGV with the lowest battery percentage from the charger queue."""
        # Use the agv.soc property (0 to 100) directly for comparison
        return min(list(self.queue), key=lambda agv: agv.soc)

    def time_to_full(self, agv) -> float:
        missing_charge = max(0.0, MAX_BATTERY - agv.battery)
        if self.charging_rate <= 0:
            raise ValueError("charging_rate must be greater than 0")
        return missing_charge / self.charging_rate
