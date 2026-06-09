"""
Entry point for the SAS Energy-Aware AGV Simulation.
"""
import ctypes
import os
import src.config as config 

# Fix blurry text (Tkinter DPI awareness) on Windows
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

import logging
import salabim as sim
from src.core.simulation import SimulationEngine
from src.config import SAVE_SUMMARY_TO_FILE, TOTAL_MIN, LOG_LEVEL, SAVE_LOG_TO_FILE, MAX_PAYLOAD
from src.utils.paths import LOGS_DIR
from src.utils.logger import setup_logger
import pandas as pd
import numpy as np

# Initialize custom logger
setup_logger(
    level=LOG_LEVEL,
    save_to_file=SAVE_LOG_TO_FILE,
    log_file=LOGS_DIR / "simulation.log"
)
logger = logging.getLogger(__name__)

#normal code for log and run 
if __name__ == "__main__":
    logger.info("Initializing Simulation Engine...")
    
   

    engine = None
    try:
        with SimulationEngine() as engine:
            logger.info(f"--- Simulation of ({TOTAL_MIN} mins) ---")
            engine.run(till=TOTAL_MIN)
            
            logger.info("--- Simulation Completed Successfully! ---")
            
            # Report KPIs
            engine.metrics.report(save_to_file=SAVE_SUMMARY_TO_FILE)
            
            # # additional for verification orders
            # print("\nORDER TRACE")
            # print("=" * 40)

            # for order in engine.order_generator.orders:
            #     print(f"\nOrder {order.order_id}")
            #     print("Time [min] | Event")
            #     print("-" * 40)
            #     for t, event in order.event_log:
            #         print(f"{t:8.2f} | {event}")
            
            #additional for verification battery 
            # battery_logs = []
            # for agv in engine.agvs:
            #     battery_logs.extend(agv.battery_log)

            # battery_df = pd.DataFrame(battery_logs)
            # battery_df.to_csv(LOGS_DIR / "agv_battery_log.csv", index=False)

            # logger.info(f"Battery log saved to {LOGS_DIR / 'agv_battery_log.csv'}")

            # additional for verification payload
            # print(f"Configured max payload = {MAX_PAYLOAD:.2f} kg\n")

            # for agv in engine.agvs:
            #     violated = agv.max_payload_observed > MAX_PAYLOAD

            #     print(
            #         f"AGV {agv.agv_id}: "
            #         f"Max payload = {agv.max_payload_observed:.2f} kg | "
            #         f"Max items = {agv.max_items_observed} | "
            #         f"Constraint violated = {violated}"
            #     )

            #additional for serivice time verification
            # for server in engine.servers:
            #     print(f"\nServer {server.server_id}")

            #     for n_items, times in sorted(server.service_time_stats.items()):
            #         avg_time = sum(times) / len(times)

            #         print(
            #             f"{n_items} item(s): "
            #             f"avg = {avg_time:.2f} min "
            #             f"(n={len(times)})"
            #         )
            

            # #additional for verification battery depletion
            # trip_logs = []
            # for agv in engine.agvs:
            #     trip_logs.extend(agv.trip_log)
            # trip_df = pd.DataFrame(trip_logs)
            # trip_df.to_csv(LOGS_DIR / "agv_trip_log.csv", index=False)
            
    except sim.SimulationStopped:
        logger.warning("--- Simulation manually stopped by user. Generating partial report... ---")
        if engine:
            try:
                # Aggregate and calculate metrics for the time elapsed so far
                engine.finalize_metrics()
                engine.metrics.report(save_to_file=SAVE_SUMMARY_TO_FILE)
            except Exception as e:
                logger.error(f"Could not generate partial report: {e}")
                
    except Exception as e:
        logger.error("--- Simulation Crashed! ---")
        logger.exception(e)
        raise e

#for experimetns new code
# if __name__ == "__main__":
#     logger.info("Initializing Simulation Engine...")

#     results = []

#     for seed in range(1000, 1010):
#         logger.info(f"--- Starting simulation run with seed {seed} ---")

#         engine = None
#         try:
#             with SimulationEngine(random_seed=seed) as engine:
#                 engine.run(till=TOTAL_MIN)

#                 m = engine.metrics
#                 run_duration_hr = m.sim_duration_min / 60

#                 results.append({
#                     "seed": seed,
#                     "orders_generated": m.total_orders_generated,
#                     "orders_fulfilled": m.total_orders_completed,
#                     "pending_orders": m.pending_orders,
#                     "in_progress_orders": m.in_progress_orders,
#                     "energy_wh": m.energy_consumed_wh,
#                     "energy_per_order": m.energy_consumed_wh / m.total_orders_completed if m.total_orders_completed > 0 else 0,
#                     "specific_energy_wh_per_kg": m.energy_consumed_wh / m.total_mass_delivered if m.total_mass_delivered > 0 else 0,
#                     "avg_distance_per_order": m.total_distance_traveled / m.total_orders_completed if m.total_orders_completed > 0 else 0,
#                     "avg_throughput": m.total_orders_completed / run_duration_hr if run_duration_hr > 0 else 0,
#                     "peak_throughput": m.peak_throughput_hr,
#                     "avg_cycle_time": np.mean(m.order_fulfillment_times) if m.order_fulfillment_times else 0,
#                     "p95_cycle_time": np.percentile(m.order_fulfillment_times, 95) if m.order_fulfillment_times else 0,
#                     "max_cycle_time": np.max(m.order_fulfillment_times) if m.order_fulfillment_times else 0,
#                     "min_fleet_soc": m.min_fleet_soc,
#                     "avg_batching_delay": np.mean(m.batching_delays) if m.batching_delays else 0,
#                     "avg_packing_queue_time": m.avg_packing_queue_min,
#                     "avg_edges_traversed": m.total_stops / m.total_tasks_completed if m.total_tasks_completed > 0 else 0,
#                 })

#         except Exception as e:
#             logger.error(f"--- Simulation Crashed for seed {seed}! ---")
#             logger.exception(e)
#             raise e

#     df = pd.DataFrame(results)

#     output_file = LOGS_DIR / "E9.csv"
#     df.to_csv(output_file, index=False)

#     print(f"\nSaved 10-run experiment results to: {output_file}")
#     print(df)