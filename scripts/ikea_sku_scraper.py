"""Web scraper that extracts all IKEA SKUs from the product sitemaps."""

import requests
import re
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_FILE = "ikea_skus_NL.txt"
BASE_URL = "https://www.ikea.com/sitemaps/prod-nl-NL"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Get the directory of the project root (one level up from /scripts)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
output_dir = os.path.join(project_root, "data")
output_file = os.path.join(output_dir, OUTPUT_FILE)

def fetch_skus():
    """Fetch SKUs by iterating through available sitemaps."""
    all_skus = set()
    i = 1
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    while True:
        sitemap_url = f"{BASE_URL}_{i}.xml"
        logger.info(f"Fetching {sitemap_url}...")
        
        try:
            response = requests.get(sitemap_url, headers=HEADERS, timeout=15)
            
            if response.status_code == 404:
                logger.info(f"Reached end of sitemaps at index {i-1}.")
                break
                
            response.raise_for_status()
            
            # Use Regex to find every 8-digit code at the end of a URL
            # Patterns like -12345678/ or -s12345678/
            skus = re.findall(r'-[sS]?(\d{8})/', response.text)
            if not skus:
                logger.warning(f"No SKUs found in {sitemap_url}")
            
            all_skus.update(skus)
            i += 1
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {sitemap_url}: {e}")
            break

    return sorted(list(all_skus))

if __name__ == "__main__":
    unique_skus = fetch_skus()

    if unique_skus:
        logger.info(f"Found {len(unique_skus)} unique article codes!")
        try:
            with open(output_file, "w") as f:
                for sku in unique_skus:
                    f.write(sku + "\n")
            logger.info(f"Successfully saved SKUs to {output_file}")
        except IOError as e:
            logger.error(f"Failed to write to {output_file}: {e}")
    else:
        logger.error("No SKUs found. Output file not updated.")