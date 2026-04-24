"""
IKEA Product Details Scraper
Extracts dimensions and weights for IKEA SKUs using multi-threading.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import re
import logging
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# File Paths
INPUT_FILE = os.path.join(DATA_DIR, "ikea_skus_NL.txt")
OUTPUT_FILE = os.path.join(DATA_DIR, "ikea_products_NL.csv")
CHECKPOINT_FILE = os.path.join(LOGS_DIR, "scraper_checkpoint.txt")
LOG_FILE = os.path.join(LOGS_DIR, "scraper.log")

# ---------- Scraping Settings ----------------
BASE_URL = "https://www.ikea.com/nl/en/p/"
PROCESS_LIMIT = 1000 # Set to None for full run
BATCH_SIZE = 50

MAX_THREADS = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
# ---------------------------------------------

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def parse_measurements(text):
    """Extracts the first floating point number from a string."""
    if not text: return None
    clean_text = text.replace(",", ".")
    match = re.search(r"(\d+\.?\d*)", clean_text)
    return float(match.group(1)) if match else None

def scrape_sku(sku):
    """Scrapes a single SKU and returns its details or an error."""
    url = f"{BASE_URL}{sku}/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return None, f"HTTP {response.status_code}"
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Extract Name
        name_tag = soup.find("span", class_="pipcom-price-module__product-name")
        if not name_tag: 
            name_tag = soup.find("span", class_="pip-header-section__title--big")
        if not name_tag:
            name_tag = soup.find("h1")
        name = name_tag.get_text(strip=True) if name_tag else "Unknown"
        
        # 2. Extract Packages
        packages = []
        measurements_div = soup.find("div", class_="pipf-measurements-modal__package-container")
        if not measurements_div:
            # Fallback for some page variants
            measurements_div = soup.find(lambda tag: tag.name == "div" and "Weight" in tag.text and ("Package" in tag.text or "Pakket" in tag.text))

        if measurements_div:
            # Get package containers
            package_divs = measurements_div.find_all("div", recursive=False)
            if not package_divs: 
                package_divs = [measurements_div]
                 
            for pkg in package_divs:
                pkg_data = {"length": 0.0, "width": 0.0, "height": 0.0, "weight": 0.0}
                # Look specifically for <li> items which contain "Label: Value"
                items = pkg.find_all("li")
                for item in items:
                    text = item.get_text(separator=" ", strip=True)
                    val = parse_measurements(text)
                    if val is not None:
                        if "Length" in text: pkg_data["length"] = val
                        elif "Width" in text: pkg_data["width"] = val
                        elif "Height" in text: pkg_data["height"] = val
                        elif "Weight" in text: pkg_data["weight"] = val
                        elif "Diameter" in text:
                            pkg_data["width"] = val
                            pkg_data["height"] = val
                
                # Extract package count
                count = 1
                count_item = pkg.find("span", class_="pipf-measurements-modal__package-measurement-value")
                if count_item:
                    try: count = int(count_item.get_text(strip=True))
                    except: count = 1
                
                for _ in range(count):
                    packages.append(pkg_data)
        
        if not packages:
            return None, "No dimensions found"

        total_weight = sum(p["weight"] for p in packages)
        max_length = max(p["length"] for p in packages)
        max_width = max(p["width"] for p in packages)
        max_height = max(p["height"] for p in packages)
        
        return {
            "SKU": sku,
            "Name": name,
            "Length": max_length,
            "Width": max_width,
            "Height": max_height,
            "Weight": round(total_weight, 3),
            "URL": url
        }, None
        
    except Exception as e:
        return None, str(e)

def main():
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Input file not found: {INPUT_FILE}")
        return

    # Clear output file if starting from scratch (checkpoint 0 or doesn't exist)
    start_idx = 0
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                start_idx = int(f.read().strip())
        except: pass
    
    if start_idx == 0 and os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        logger.info(f"Clean start: removed existing {OUTPUT_FILE}")

    with open(INPUT_FILE, "r") as f:
        skus = [line.strip() for line in f if line.strip()]

    end_idx = len(skus)
    if PROCESS_LIMIT:
        end_idx = min(start_idx + PROCESS_LIMIT, len(skus))

    if start_idx >= end_idx:
        logger.info("All items already processed or limit reached.")
        return

    logger.info(f"Starting crawl: {start_idx} to {end_idx}")
    cols = ["SKU", "Name", "Length", "Width", "Height", "Weight", "URL"]

    for i in range(start_idx, end_idx, BATCH_SIZE):
        batch_end = min(i + BATCH_SIZE, end_idx)
        batch_skus = skus[i:batch_end]
        
        results = []
        errors = []
        
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            future_to_sku = {executor.submit(scrape_sku, sku): sku for sku in batch_skus}
            
            for future in tqdm(as_completed(future_to_sku), total=len(batch_skus), desc=f"Batch {i//BATCH_SIZE + 1}"):
                sku = future_to_sku[future]
                try:
                    data, err = future.result()
                    if data:
                        results.append(data)
                    if err:
                        errors.append(f"{sku}: {err}")
                except Exception as e:
                    errors.append(f"{sku}: {str(e)}")
        
        if results:
            df = pd.DataFrame(results)[cols]
            header = not os.path.exists(OUTPUT_FILE)
            df.to_csv(OUTPUT_FILE, mode='a', index=False, header=header)
        
        if errors:
            with open(os.path.join(LOGS_DIR, "scraper_errors.log"), "a") as f:
                for e in errors: f.write(e + "\n")
        
        with open(CHECKPOINT_FILE, "w") as f:
            f.write(str(batch_end))
            
        logger.info(f"Batch {i//BATCH_SIZE + 1} finished. Total processed: {batch_end}")

if __name__ == "__main__":
    main()
