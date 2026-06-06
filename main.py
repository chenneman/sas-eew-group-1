"""
Entry point for the SAS Energy-Aware AGV Simulation.
"""
import ctypes
import os

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

# Initialize custom logger
setup_logger(
    level=LOG_LEVEL,
    save_to_file=SAVE_LOG_TO_FILE,
    log_file=LOGS_DIR / "simulation.log"
)
logger = logging.getLogger(__name__)

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
            
            # additional for verification orders
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
            print(f"Configured max payload = {MAX_PAYLOAD:.2f} kg\n")

            for agv in engine.agvs:
                violated = agv.max_payload_observed > MAX_PAYLOAD

                print(
                    f"AGV {agv.agv_id}: "
                    f"Max payload = {agv.max_payload_observed:.2f} kg | "
                    f"Max items = {agv.max_items_observed} | "
                    f"Constraint violated = {violated}"
                )

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
