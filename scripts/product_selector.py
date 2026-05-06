"""
Product Selector
Filters scraped IKEA products based on weight and dimension constraints
for simulation purposes.
"""

import pandas as pd
import os
import logging
import random

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# File Paths
INPUT_FILE = os.path.join(DATA_DIR, "ikea_products_NL.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "selected_simulation_items.csv")
LOG_FILE = os.path.join(LOGS_DIR, "selector.log")

# --- Logging Setup ---
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Parameters ---
PRODUCT_COUNT = 100       # Total items to pick for the simulation
MAX_ITEM_WEIGHT = 40   # Maximum weight per individual item (kg)
MAX_DIMENSION = 40    # Maximum size for the LONGEST side of an item (cm)
RANDOM_SEED = 123        # For reproducible selection

def main():
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Input file not found: {INPUT_FILE}. Please run the details scraper first.")
        return

    logger.info(f"Loading products from {INPUT_FILE}...")
    try:
        df = pd.read_csv(INPUT_FILE)
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return

    # 1. Clean data
    # Filter out items where dimensions were not found or are zero
    initial_count = len(df)
    df = df.dropna(subset=['Length', 'Width', 'Height', 'Weight'])
    df = df[(df['Length'] > 0) & (df['Width'] > 0) & (df['Height'] > 0)]
    
    cleaned_count = len(df)
    if initial_count > cleaned_count:
        logger.info(f"Removed {initial_count - cleaned_count} items with missing/zero dimensions.")

    # 2. Orientation-Agnostic Dimension Filter
    # We check if the longest side of the product fits within our MAX_DIMENSION
    def fits_constraints(row):
        dims = sorted([row['Length'], row['Width'], row['Height']])
        # Constraint: Longest side must be <= MAX_DIMENSION
        # and Weight must be <= MAX_ITEM_WEIGHT
        if row['Weight'] > MAX_ITEM_WEIGHT:
            return False
        if dims[-1] > MAX_DIMENSION:
            return False
        return True

    logger.info(f"Filtering items (Weight <= {MAX_ITEM_WEIGHT}kg, Max Side <= {MAX_DIMENSION}cm)...")
    valid_mask = df.apply(fits_constraints, axis=1)
    filtered_df = df[valid_mask].copy()
    
    total_valid = len(filtered_df)
    if total_valid == 0:
        logger.error("No items found matching your criteria.")
        return

    logger.info(f"Found {total_valid} valid items.")

    # 3. Selection
    # If we have fewer than requested, we allow replacement to fill the quota
    replace = total_valid < PRODUCT_COUNT
    if replace:
        logger.warning(f"Only {total_valid} unique items match. Sampling with replacement to reach {PRODUCT_COUNT}.")
    
    selected_df = filtered_df.sample(
        n=PRODUCT_COUNT, 
        replace=replace, 
        random_state=RANDOM_SEED
    ).copy()

    # 4. Calculation & Export
    selected_df['Volume_cm3'] = selected_df['Length'] * selected_df['Width'] * selected_df['Height']
    
    final_cols = ['SKU', 'Name', 'Weight', 'Length', 'Width', 'Height', 'Volume_cm3', 'URL']
    result = selected_df[final_cols]

    result.to_csv(OUTPUT_FILE, index=False)
    
    logger.info(f"Successfully selected {PRODUCT_COUNT} items.")
    logger.info(f"Average weight: {result['Weight'].mean():.2f} kg")
    logger.info(f"Average Volume: {result['Volume_cm3'].mean():.2f} cm3")
    logger.info(f"Results saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
