"""Main entry point for the simulation"""

from entities.item import load_items

items = load_items()
for item in items:
    print(item.sku)