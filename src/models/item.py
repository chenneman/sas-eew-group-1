"""Item model and loading utilities."""

from dataclasses import dataclass
import pandas as pd
from pathlib import Path
from src.utils.paths import SELECTED_ITEMS_CSV

@dataclass(frozen=False)
class Item:
    sku: int
    name: str
    weight: float
    length: float
    width: float
    height: float
    volume: float
    url: str
    shelf_location: tuple[int, int] | None = None

def load_items(csv_path: str | Path = SELECTED_ITEMS_CSV) -> list[Item]:
    """
    Loads items from a CSV file and returns a list of Item objects.
    
    Args:
        csv_path: Path to the CSV file. Defaults to SELECTED_ITEMS_CSV.
        
    Returns:
        list[Item]: A list of Item instances.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Simulation items file not found at: {path.absolute()}")

    df = pd.read_csv(path)
    
    # Ensure SKU is treated as int to preserve formatting if any
    df['SKU'] = df['SKU'].astype(int)
    
    items = []
    for _, row in df.iterrows():
        items.append(Item(
            sku=row['SKU'],
            name=row['Name'],
            weight=float(row['Weight']),
            length=float(row['Length']),
            width=float(row['Width']),
            height=float(row['Height']),
            volume=float(row['Volume_cm3']),
            url=row['URL']
        ))
    
    return items
