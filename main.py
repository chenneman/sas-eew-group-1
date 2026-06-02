"""
Entry point for the SAS Energy-Aware AGV Simulation.
"""

from src.core.simulation import SimulationEngine

if __name__ == "__main__":
    print("Initializing Simulation Engine...")
    
    # Instantiate the simulation engine with tracing on for our tiny integration test
    engine = SimulationEngine(trace=True, animate=False)
    
    #  run for a very short duration first (60 minutes) to verify no immediate crashes
    test_duration = 60
    
    print(f"\n--- Starting Tiny Integration Test ({test_duration} mins) ---")
    try:
        engine.run(till=test_duration)
        print("\n--- Tiny Integration Test Completed Successfully! ---")
        
        # In the future, this will run for TOTAL_MIN and generate reports
        # engine.run(till=TOTAL_MIN)
        
    except Exception as e:
        print(f"\n--- Simulation Crashed! ---")
        raise e