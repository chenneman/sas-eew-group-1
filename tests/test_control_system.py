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
            Node(4, (3, 0), NodeType.PACKING),
        ]

        for node in nodes:
            self.routing_graph.add_node(node)

        self.routing_graph.add_edge(1, 2)
        self.routing_graph.add_edge(2, 3)
        self.routing_graph.add_edge(3, 4)

        self.idle_spot_node_ids = [1]
        self.packing_station_node_ids = [4]

        self.location_to_node_id = {
            (1, 0): 2,
            (2, 0): 3,
        }


class MockAGV:
    def __init__(self, agv_id):
        self.agv_id = agv_id
        self.status = AGVStatus.IDLE
        self.soc = 621.6
        self.current_task = None
        self.route = None
        self.orders = []


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
        shelf_location=(1, 0),
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
        shelf_location=(2, 0),
    )

    order1 = TOrder(arrival_sim_min=0, item=item1)
    order2 = TOrder(arrival_sim_min=0, item=item2)
    order_queue.append(order1)
    order_queue.append(order2)

    agvs = [
        MockAGV(1),
        MockAGV(2),
    ]

    control_system = TControlSystem(
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

