"""
Animation utilities for translating grid coordinates to screen pixels.
"""

# Pixel scale factor: 1 grid unit = 30 pixels
ANIMATION_SCALE = 30

# Offset to center elements within the 30x30 cell
ANIMATION_OFFSET = 15

def grid_to_pixel(grid_coord: float) -> float:
    """
    Translates a raw warehouse grid coordinate to a screen pixel coordinate.
    
    Args:
        grid_coord: The coordinate in meters/grid-units.
        
    Returns:
        The coordinate in pixels for Salabim animation.
    """
    return grid_coord * ANIMATION_SCALE + ANIMATION_OFFSET
