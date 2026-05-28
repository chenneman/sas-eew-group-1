import salabim as sim

from src.models.agv import AGVStatus
from src.models.charger import TCharger


class MockAGV(sim.Component):
    def setup(self, queue, agv_id, soc, max_battery=100.0, current_node=2, routing_graph=None):
        self.queue = queue
        self.agv_id = agv_id
        self.soc = soc
        self.max_battery = max_battery
        self.current_node = current_node
        self.next_node = current_node
        self.routing_graph = routing_graph
        self.graph = routing_graph._graph if routing_graph is not None else None
        self.route = []
        self.status = AGVStatus.CHARGING
        self.reactivated_at = None

    def process(self):
        self.enter(self.queue)
        yield self.passivate()
        self.reactivated_at = self.env.now()


def make_graph():
    class FakeNodeView:
        def __init__(self, node_data):
            self.node_data = node_data

        def __call__(self, data=False):
            if data:
                return list(self.node_data.items())
            return list(self.node_data)

    class FakeNetworkGraph:
        def __init__(self):
            self.nodes = FakeNodeView({
                1: {"type": "IDLE"},
                2: {"type": "CHARGING"},
                3: {"type": "CHARGING"},
            })

    class FakeRoutingGraph:
        def __init__(self):
            self._graph = FakeNetworkGraph()

        def get_shortest_path(self, start_id, end_id):
            return [start_id, end_id]

    return FakeRoutingGraph()


def test_charger_selects_highest_battery_percentage_first():
    env = sim.Environment(trace=False)
    queue = sim.Queue("ChargerQueue")
    graph = make_graph()

    low = MockAGV(queue=queue, agv_id=1, soc=20, current_node=2, routing_graph=graph)
    high = MockAGV(queue=queue, agv_id=2, soc=80, current_node=3, routing_graph=graph)
    TCharger(
        charger_id=1,
        queue=queue,
        routing_graph=graph,
        idle_node_id=1,
        charging_rate=10,
        poll_interval=0.1,
    )

    env.run(till=3)

    assert high.soc == high.max_battery
    assert high.current_node == 1
    assert high.next_node == 1
    assert high.status == AGVStatus.IDLE
    assert high.reactivated_at == 2
    assert low.reactivated_at is None


def test_charger_moves_full_agv_to_idle_spot():
    env = sim.Environment(trace=False)
    queue = sim.Queue("ChargerQueue")
    graph = make_graph()

    agv = MockAGV(queue=queue, agv_id=1, soc=100, current_node=2, routing_graph=graph)
    TCharger(
        charger_id=1,
        queue=queue,
        routing_graph=graph,
        idle_node_id=1,
        charging_rate=10,
        poll_interval=0.1,
    )

    env.run(till=1)

    assert agv.soc == agv.max_battery
    assert agv.current_node == 1
    assert agv.route == [2, 1]
    assert agv.status == AGVStatus.IDLE
    assert agv.reactivated_at == 0
