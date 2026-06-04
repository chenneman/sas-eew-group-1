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
from src.core.simulation import SimulationEngine
from src.config import SAVE_SUMMARY_TO_FILE, TOTAL_MIN, LOG_LEVEL, SAVE_LOG_TO_FILE
from src.utils.paths import LOGS_DIR
from src.utils.logger import setup_logger

# Initialize custom logger
setup_logger(
    level=LOG_LEVEL,
    save_to_file=SAVE_LOG_TO_FILE,
    log_file=LOGS_DIR / "simulation.log"
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Initializing Simulation Engine...")

    try:
        with SimulationEngine() as engine:
            logger.info(f"--- Simulation of ({TOTAL_MIN} mins) ---")
            engine.run(till=TOTAL_MIN)
            
            logger.info("--- Simulation Completed Successfully! ---")
            
            # Report KPIs
            engine.metrics.report(save_to_file=SAVE_SUMMARY_TO_FILE)
            
    except Exception as e:
        logger.error("--- Simulation Crashed! ---")
        logger.exception(e)
        raise e
