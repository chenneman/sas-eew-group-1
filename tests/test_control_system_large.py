import salabim as sim

from src.models.graph import RoutingGraph, Node, NodeType
from src.models.item import Item
from src.models.order_generator import TOrder
from src.models.controlsystem import TControlSystem
from src.models.agv import AGVStatus


class MockWarehouse:
    def __init__(self):
        self.routing_graph = RoutingGraph()

        nodes = [
            Node(1, (0, 0), NodeType.IDLE),
            Node(2, (1, 0), NodeType.SHELF),
            Node(3, (2, 0), NodeType.SHELF),
            Node(4, (3, 0), NodeType.SHELF),
            Node(5, (4, 0), NodeType.PACKING),
            Node(6, (2, 1), NodeType.SHELF),
        ]

        for node in nodes:
            self.routing_graph.add_node(node)

        edges = [
            (1, 2),
            (2, 3),
            (3, 4),
            (4, 5),
            (3, 6),
            (6, 5),
        ]

        for i, j in edges:
            self.routing_graph.add_edge(i, j)

        self.idle_spot_node_ids = [1]
        self.packing_station_node_ids = [5]

        self.location_to_node_id = {
            (1, 0): 2,
            (2, 0): 3,
            (3, 0): 4,
            (2, 1): 6,
        }


class MockAGV:
    def __init__(self, agv_id):
        self.agv_id = agv_id
        self.status = AGVStatus.IDLE
        self.soc = 621.6
        self.current_task = None
        self.route = None
        self.orders = []


def make_item(sku, name, weight, volume, shelf_location):
    return Item(
        sku=sku,
        name=name,
        weight=weight,
        length=1,
        width=1,
        height=1,
        volume=volume,
        url="",
        shelf_location=shelf_location,
    )


def run_test():
    env = sim.Environment(trace=False)

    warehouse = MockWarehouse()
    order_queue = []

    items = [
        make_item(1, "Box 1", 10.0, 1000, (1, 0)),
        make_item(2, "Box 2", 15.0, 1000, (2, 0)),
        make_item(3, "Box 3", 20.0, 1000, (3, 0)),
        make_item(4, "Box 4", 8.0, 1000, (2, 1)),
    ]

    orders = [
        TOrder(arrival_sim_min=0, item=item)
        for item in items
    ]

    order_queue.extend(orders)

    agvs = [
        MockAGV(1),
        MockAGV(2),
    ]

    control_system = TControlSystem(
        warehouse=warehouse,
        order_queue=order_queue,
        available_agvs=agvs,
        batch_size=4,
        max_wait_time=5,
    )

    control_system.agvs = agvs

    tasks = control_system.routing_algorithm(
        orders=list(order_queue),
        available_agvs=agvs,
    )

    print("\n===== CONTROL SYSTEM TEST RESULTS =====")

    assigned_order_ids = []

    for task in tasks:
        total_weight = sum(order.item.weight for order in task.orders)

        assigned_ids = [order.order_id for order in task.orders]
        assigned_order_ids.extend(assigned_ids)

        print("--------------------------------------")
        print(f"AGV: {task.agv.agv_id}")
        print(f"Orders assigned: {assigned_ids}")
        print(f"Total weight: {total_weight} kg")
        print(f"Route node IDs: {task.route}")

    print("--------------------------------------")

    waiting_orders = [
        order.order_id
        for order in orders
        if order.order_id not in assigned_order_ids
    ]

    print(f"Orders still waiting in queue: {waiting_orders}")

    print("======================================\n")


if __name__ == "__main__":
    run_test()