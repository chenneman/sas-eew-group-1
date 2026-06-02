import salabim as sim

from components.server import Server
from entities.item import Item
from entities.order import Order
from entities.task import Task
from components.agv import AGVStatus


class MockAGV(sim.Component):
    def setup(self, agv_id, queue):
        self.agv_id = agv_id
        self.status = AGVStatus.MOVING
        self.current_task = None
        self.queue = queue

    def complete_task(self):
        self.current_task = None

    def process(self):
        self.passivate()


def run_test():
    env = sim.Environment(trace=True)

    server_queue = sim.Queue("server_queue")
    processed_orders = []

    server = Server(
        server_id=1,
        queue=server_queue,
        processed_orders=processed_orders
    )

    # Create test data
    item1 = Item(sku=1, name="Box 1", weight=4.0, length=1, width=1, height=1, volume=1000, url="",
                 node_id=2)
    order1 = Order(order_id=1, arrival_min=0, item=item1)

    task = Task(task_id=1, orders=[order1])

    agv = MockAGV(agv_id=1, queue=server_queue)
    agv.current_task = task
    task.agv = agv

    # Put AGV in queue to trigger server
    agv.enter(server_queue)

    print("\nStarting simulation...")
    env.run(till=100)

    print("\nResults:")
    print(f"AGV final status: {agv.status}")
    print(f"AGV current task (should be None): {agv.current_task}")
    print(f"Processed orders: {[o.order_id for o in processed_orders]}")
    print(f"Item status: {item1.status}")


if __name__ == "__main__":
    run_test()
