"""Path utilities for consistent directory access across the project."""

from pathlib import Path

# Project root is 2 levels up from this file (src/utils/paths.py)
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

# Major directory paths
DATA_DIR = PROJECT_ROOT / "data"
SRC_DIR = PROJECT_ROOT / "src"
LOGS_DIR = PROJECT_ROOT / "logs"
TESTS_DIR = PROJECT_ROOT / "tests"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Specific file paths
SELECTED_ITEMS_CSV = DATA_DIR / "selected_simulation_items.csv"
IKEA_PRODUCTS_CSV = DATA_DIR / "ikea_products_NL.csv"

def ensure_directories():
    """Creates essential directories if they don't exist."""
    for directory in [DATA_DIR, LOGS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    # Quick debug output to verify paths
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Data Dir:     {DATA_DIR}")
    print(f"Selected CSV: {SELECTED_ITEMS_CSV}")
    print(f"Exists:       {SELECTED_ITEMS_CSV.exists()}")
