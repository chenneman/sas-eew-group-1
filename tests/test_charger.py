import salabim as sim
from src.components.charger import Charger
from src.components.agv import AGVStatus

from src.config import MAX_BATTERY


class MockAGV(sim.Component):
    def setup(self, agv_id, queue, current_battery):
        self.agv_id = agv_id
        self.status = AGVStatus.MOVING
        self.battery = current_battery
        self.queue = queue
        self.charge_completion_time = None

    @property
    def soc(self) -> float:
        return self.battery / MAX_BATTERY * 100

    def process(self):
        self.passivate()
        # When activated by the charger, record the time
        self.charge_completion_time = self.env.now()


def run_test():
    env = sim.Environment(trace=False)

    charger_queue = sim.Queue("charger_queue")

    # Use a clean 10.0 Wh/min for predictable math in the test
    test_charging_rate = 10.0

    charger = Charger(
        charger_id=1,
        queue=charger_queue,
        charging_rate=test_charging_rate
    )

    # AGV 1: 50% battery (missing 310.8 Wh)
    agv1 = MockAGV(agv_id=1, queue=charger_queue, current_battery=310.8)
    # AGV 2: 10% battery (missing 559.44 Wh)
    agv2 = MockAGV(agv_id=2, queue=charger_queue, current_battery=62.16)

    agv1.enter(charger_queue)
    agv2.enter(charger_queue)

    env.run(till=200)

    # Mathematical expectations
    agv1_charge_time = (MAX_BATTERY - 310.8) / test_charging_rate  # 31.08
    agv2_charge_time = (MAX_BATTERY - 62.16) / test_charging_rate  # 55.944

    # Because AGV 1 has higher SOC (50% > 10%), it should be charged FIRST
    # AGV 2 should finish charging after AGV 1 is done

    expected_agv1_time = agv1_charge_time
    expected_agv2_time = agv1_charge_time + agv2_charge_time

    # Assertions
    assert abs(agv1.battery - MAX_BATTERY) < 0.001, f"AGV1 battery not full: {agv1.battery}"
    assert agv1.status == AGVStatus.IDLE, f"AGV1 wrong status: {agv1.status}"
    assert abs(
        agv1.charge_completion_time - expected_agv1_time) < 0.001, f"AGV1 wrong completion time: {agv1.charge_completion_time} != {expected_agv1_time}"

    assert abs(agv2.battery - MAX_BATTERY) < 0.001, f"AGV2 battery not full: {agv2.battery}"
    assert agv2.status == AGVStatus.IDLE, f"AGV2 wrong status: {agv2.status}"
    assert abs(
        agv2.charge_completion_time - expected_agv2_time) < 0.001, f"AGV2 wrong completion time: {agv2.charge_completion_time} != {expected_agv2_time}"

    print("Charger tests passed! AGVs were processed in correct SOC order and charged fully.")


if __name__ == "__main__":
    run_test()