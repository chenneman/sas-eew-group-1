"""
Entry point for the SAS Energy-Aware AGV Simulation.
"""

from src.core.simulation import SimulationEngine

if __name__ == "__main__":
    print("Initializing Simulation Engine...")
    
    # Instantiate the simulation engine with animation on
    engine = SimulationEngine(trace=False, animate=True)
    
    #  run for a very short duration first (60 minutes) to verify no immediate crashes
    test_duration = 300
    
    print(f"\n--- Starting Tiny Integration Test ({test_duration} mins) ---")
    try:
        engine.run(till=test_duration)
        print("\n--- Tiny Integration Test Completed Successfully! ---")
        
        # Report KPIs
        engine.metrics.report()
        
        # In the future, this will run for TOTAL_MIN and generate reports
        # engine.run(till=TOTAL_MIN)
        
    except Exception as e:
        print(f"\n--- Simulation Crashed! ---")
        raise e