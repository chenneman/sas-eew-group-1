"""
Entry point for the SAS Energy-Aware AGV Simulation.
"""

from src.core.simulation import SimulationEngine
from src.config import SAVE_SUMMARY_TO_FILE, TOTAL_MIN, ANIMATE

if __name__ == "__main__":
    print("Initializing Simulation Engine...")
    
    # Instantiate the simulation engine with animation on
    engine = SimulationEngine(trace=False, animate=ANIMATE)
    
    print(f"\n--- Simulation of ({TOTAL_MIN} mins) ---")
    try:
        engine.run(till=TOTAL_MIN)
        print("\n--- Simulation Completed Successfully! ---")
        
        # Report KPIs
        engine.metrics.report(save_to_file=SAVE_SUMMARY_TO_FILE)
        
    except Exception as e:
        print(f"\n--- Simulation Crashed! ---")
        raise e