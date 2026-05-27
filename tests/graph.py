"""
Manual test script for the warehouse RoutingGraph.
"""

from src.models.graph import RoutingGraph, Node, NodeType


def run_manual_test():
    # 1. Initialize the graph wrapper
    rg = RoutingGraph()

    # 2. Create a mini warehouse layout (coordinates in meters)
    nodes = [
        Node(node_id=1, coords=(0, 0), node_type=NodeType.CHARGING),
        Node(node_id=2, coords=(0, 10), node_type=NodeType.IDLE),
        Node(node_id=3, coords=(10, 10), node_type=NodeType.SHELF),
        Node(node_id=4, coords=(10, 0), node_type=NodeType.PACKING),
        Node(node_id=5, coords=(5, 5), node_type=NodeType.IDLE),  # Center node
    ]

    print("Adding nodes to the graph...")
    for node in nodes:
        rg.add_node(node)

    # 3. Connect the nodes
    print("Connecting edges...")
    # Perimeter
    rg.add_edge(1, 2)
    rg.add_edge(2, 3)
    rg.add_edge(3, 4)
    rg.add_edge(4, 1)

    # Cross paths through the center node
    rg.add_edge(1, 5)
    rg.add_edge(5, 3)

    # 4. Test Pathfinding
    start_node = 1
    end_node = 3

    print(f"\n--- Pathfinding Test ---")
    print(f"Calculating shortest path from Node {start_node} to Node {end_node}...")

    # This should logically go [1 -> 5 -> 3] because it's a direct diagonal,
    # instead of taking the perimeter [1 -> 2 -> 3] or [1 -> 4 -> 3].
    optimal_path = rg.get_shortest_path(start_id=start_node, end_id=end_node)

    print(f"Resulting route: {optimal_path}")

    # 5. Visual Check
    print("\nOpening layout visualization (close the window to end the script)...")
    rg.visualize()


if __name__ == "__main__":
    run_manual_test()