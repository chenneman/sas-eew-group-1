"""
Logging utility for the SAS AGV simulation.
Provides colored console output and optional file logging.
"""

import logging
import sys
from pathlib import Path

# ANSI Escape Codes for Colors
class Colors:
    """ANSI color constants."""
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"

class ColoredFormatter(logging.Formatter):
    """Custom logging formatter that adds colors to the console output."""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BOLD + Colors.RED
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        
        # Simple format for console
        log_fmt = f"{Colors.BLUE}[%(asctime)s]{Colors.RESET} {color}%(levelname)-8s{Colors.RESET} %(message)s"
        
        # If we have a module name, add it for debug
        if record.levelno <= logging.DEBUG:
            log_fmt = f"{Colors.BLUE}[%(asctime)s]{Colors.RESET} {color}%(levelname)-8s{Colors.RESET} [%(name)s] %(message)s"
            
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)

def setup_logger(level: str = "INFO", save_to_file: bool = False, log_file: Path = None):
    """
    Configures the root logger for the entire application.
    
    Args:
        level: The logging level (DEBUG, INFO, etc.)
        save_to_file: Whether to also save logs to a file.
        log_file: The path to the log file.
    """
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(level.upper())
    
    # Remove existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. Console Handler (with colors)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    # 2. File Handler (no colors, plain text)
    if save_to_file and log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, mode='w')
        file_fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger

class UILogHandler(logging.Handler):
    """
    Custom logging handler that appends formatted log messages to a list.
    Used for mirroring terminal logs to a Salabim UI component.
    """
    def __init__(self, log_list: list, max_lines: int = 20):
        super().__init__()
        self.log_list = log_list
        self.max_lines = max_lines

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_list.append(msg)
            # Keep the list size bounded
            if len(self.log_list) > self.max_lines:
                self.log_list.pop(0)
        except Exception:
            self.handleError(record)
