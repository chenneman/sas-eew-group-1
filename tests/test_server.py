import salabim as sim

from src.models.agv import AGVStatus
from src.models.item import Item
from src.models.order_generator import TOrder
from src.models.server import TServer
from src.models.TTask import TTask


class FixedServiceTimeGenerator:
    def sample_service_time(self, n_items):
        return 2.0, 3.0


class MockAGV(sim.Component):
    def setup(self, queue, task):
        self.agv_id = 1
        self.queue = queue
        self.current_task = task
        self.route = [1, 2, 3]
        self.orders = getattr(task, "orders", [])
        self.status = AGVStatus.UNLOADING
        self.reactivated_at = None

    def process(self):
        self.enter(self.queue)
        yield self.passivate()
        self.reactivated_at = self.env.now()


def test_server_completes_orders_and_reactivates_agv():
    env = sim.Environment(trace=False)
    queue = sim.Queue("ServerQueue")
    processed_orders = []

    item = Item(
        sku=1,
        name="Box",
        weight=1.0,
        length=1.0,
        width=1.0,
        height=1.0,
        volume=1.0,
        url="",
    )
    order = TOrder(arrival_sim_min=0, item=item)
    task = TTask(orders=[order], route=[1, 2, 3], agv=None, creation_time=0)

    agv = MockAGV(queue=queue, task=task)
    task.agv = agv
    TServer(
        server_id=1,
        queue=queue,
        service_time_generator=FixedServiceTimeGenerator(),
        processed_orders=processed_orders,
        poll_interval=0.1,
    )

    env.run(till=5)

    assert item.status == "DELIVERED"
    assert order.status == "COMPLETED"
    assert order.completion_time == 3
    assert processed_orders == [order]
    assert agv.current_task is None
    assert agv.route == []
    assert agv.orders == []
    assert agv.status == AGVStatus.IDLE
    assert agv.reactivated_at == 3


def test_server_handles_task_items_without_orders():
    env = sim.Environment(trace=False)
    queue = sim.Queue("ServerQueue")

    item = Item(
        sku=2,
        name="Loose box",
        weight=1.0,
        length=1.0,
        width=1.0,
        height=1.0,
        volume=1.0,
        url="",
    )

    class TaskWithoutOrders:
        all_items = [item]

    agv = MockAGV(queue=queue, task=TaskWithoutOrders())
    TServer(
        server_id=1,
        queue=queue,
        service_time_generator=FixedServiceTimeGenerator(),
        poll_interval=0.1,
    )

    env.run(till=5)

    assert item.status == "DELIVERED"
    assert agv.current_task is None
    assert agv.status == AGVStatus.IDLE
    assert agv.reactivated_at == 3
