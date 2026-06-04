import salabim as sim

from src.environment.graph import RoutingGraph, Node, NodeType
from src.entities.item import Item
from src.entities.order import Order
from src.components.control_system import ControlSystem
from src.components.agv import AGVStatus


class MockWarehouse:
    def __init__(self):
        self.routing_graph = RoutingGraph()

        nodes = [
            Node(1, (0, 0), NodeType.IDLE),
            Node(2, (1, 0), NodeType.SHELF),
            Node(3, (2, 0), NodeType.SHELF),
            Node(4, (3, 0), NodeType.PACKING),
        ]

        for node in nodes:
            self.routing_graph.add_node(node)

        self.routing_graph.add_edge(1, 2)
        self.routing_graph.add_edge(2, 3)
        self.routing_graph.add_edge(3, 4)

        self.idle_spot_node_ids = [1]
        self.packing_station_node_ids = [4]
        self.shelf_node_ids = [2, 3]

        self.location_to_node_id = {
            (1, 0): 2,
            (2, 0): 3,
        }


class MockAGV:
    def __init__(self, agv_id, current_node=1):
        self.agv_id = agv_id
        self.status = AGVStatus.IDLE
        self.battery = 621.6 
        self.current_task = None
        self.route = None
        self.orders = []
        self.current_node = current_node


def run_test():
    env = sim.Environment(trace=False)

    warehouse = MockWarehouse()
    order_queue = []

    item1 = Item(
        sku=1,
        name="Box 1",
        weight=4.0,
        length=1,
        width=1,
        height=1,
        volume=1000,
        url="",
        node_id=2,
    )

    item2 = Item(
        sku=2,
        name="Box 2",
        weight=10.0,
        length=1,
        width=1,
        height=1,
        volume=1000,
        url="",
        node_id=3,
    )

    order1 = Order(order_id=1, arrival_min=0, item=item1)
    order2 = Order(order_id=2, arrival_min=0, item=item2)
    order_queue.append(order1)
    order_queue.append(order2)

    agvs = [
        MockAGV(1),
        MockAGV(2),
    ]

    control_system = ControlSystem(
        warehouse=warehouse,
        order_queue=order_queue,
        available_agvs=agvs,
        batch_size=2,
        max_wait_time=5,
    )

    # Important if your setup still only has self.available_agvs
    control_system.agvs = agvs

    tasks = control_system.routing_algorithm(
        orders=list(order_queue),
        available_agvs=agvs,
    )

    print("\n===== CONTROL SYSTEM TEST RESULTS =====")
    print(f"Number of tasks created: {len(tasks)}")

    for task in tasks:
        print("--------------------------------------")
        print(f"AGV: {task.agv.agv_id}")
        print(f"Orders: {[order.order_id for order in task.orders]}")
        print(f"Route node IDs: {task.route}")

    print("======================================\n")


if __name__ == "__main__":
    run_test()
