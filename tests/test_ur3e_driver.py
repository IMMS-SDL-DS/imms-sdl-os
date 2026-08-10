"""
src/pipeline/ur3e_driver.py 테스트.
실제 UR3e 로봇/ur_rtde 라이브러리 없이, get_connection()을 가짜 객체로 대체해서 검증한다.
"""

import pytest

from src.database.models import Action, ActionType
from src.pipeline import ur3e_driver


class FakeRTDE:
    """rtde_control.RTDEControlInterface 흉내 — moveL/isPoseWithinSafetyLimits만 구현."""

    def __init__(self, within_limits: bool = True, move_success: bool = True):
        self.within_limits = within_limits
        self.move_success = move_success
        self.moveL_calls: list[list[float]] = []

    def isPoseWithinSafetyLimits(self, pose):
        return self.within_limits

    def moveL(self, pose, speed, acceleration):
        self.moveL_calls.append(pose)
        return self.move_success


def _action(action_type, **kwargs) -> Action:
    return Action(
        action_id="a1", parent_task_id="t1", sequence_index=1,
        action_type=action_type, **kwargs,
    )


def test_pick_driver_moves_to_source_location(monkeypatch):
    fake = FakeRTDE()
    monkeypatch.setattr(ur3e_driver, "get_connection", lambda: fake)

    result = ur3e_driver.pick_driver(_action(ActionType.PICK, source_location="head_rack"))

    assert result["success"] is True
    assert len(fake.moveL_calls) == 1


def test_place_driver_moves_to_dest_location(monkeypatch):
    fake = FakeRTDE()
    monkeypatch.setattr(ur3e_driver, "get_connection", lambda: fake)

    result = ur3e_driver.place_driver(_action(ActionType.PLACE, dest_location="vial_rack"))

    assert result["success"] is True
    assert fake.moveL_calls[0] == ur3e_driver.LOCATION_POSES["vial_rack"]


def test_driver_fails_when_location_unknown(monkeypatch):
    fake = FakeRTDE()
    monkeypatch.setattr(ur3e_driver, "get_connection", lambda: fake)

    result = ur3e_driver.place_driver(_action(ActionType.PLACE, dest_location="어딘가_없는_곳"))

    assert result["success"] is False
    assert len(fake.moveL_calls) == 0  # 안 움직여야 함


def test_move_fails_when_outside_safety_limits(monkeypatch):
    """안전 범위 밖이면 moveL 자체를 호출하지 않아야 함 (움직이기 전에 미리 막기)."""
    fake = FakeRTDE(within_limits=False)
    monkeypatch.setattr(ur3e_driver, "get_connection", lambda: fake)

    result = ur3e_driver.retract_driver(_action(ActionType.RETRACT))

    assert result["success"] is False
    assert "safety" in result["reason"]
    assert len(fake.moveL_calls) == 0


def test_retract_driver_always_targets_home(monkeypatch):
    """RETRACT는 source/dest_location과 무관하게 항상 'home'으로 가야 함."""
    fake = FakeRTDE()
    monkeypatch.setattr(ur3e_driver, "get_connection", lambda: fake)

    ur3e_driver.retract_driver(_action(ActionType.RETRACT))

    assert fake.moveL_calls[0] == ur3e_driver.LOCATION_POSES["home"]


def test_mount_driver_moves_to_balance(monkeypatch):
    fake = FakeRTDE()
    monkeypatch.setattr(ur3e_driver, "get_connection", lambda: fake)

    result = ur3e_driver.mount_driver(_action(ActionType.MOUNT, dest_location="balance"))

    assert result["success"] is True


def test_register_ur3e_drivers_overrides_simulation():
    """register_ur3e_drivers()를 부르면 시뮬레이션 대신 실제 함수가 등록되어야 함."""
    from src.pipeline.action_driver import ACTION_DRIVERS, _simulated_driver, register_action_driver

    ur3e_driver.register_ur3e_drivers()
    try:
        assert ACTION_DRIVERS[ActionType.PICK] == ur3e_driver.pick_driver
        assert ACTION_DRIVERS[ActionType.PLACE] == ur3e_driver.place_driver
        assert ACTION_DRIVERS[ActionType.MOUNT] == ur3e_driver.mount_driver
        assert ACTION_DRIVERS[ActionType.RETRACT] == ur3e_driver.retract_driver
    finally:
        # 다른 테스트에 영향 안 주도록 시뮬레이션으로 원복
        for t in [ActionType.PICK, ActionType.PLACE, ActionType.MOUNT, ActionType.RETRACT]:
            register_action_driver(t, _simulated_driver)


def test_get_connection_raises_clear_error_without_ur_rtde_installed(monkeypatch):
    """ur_rtde 미설치 환경에서, 에러 원인을 명확히 알려주는지."""
    monkeypatch.setattr(ur3e_driver, "rtde_control", None)
    monkeypatch.setattr(ur3e_driver, "_connection", None)

    with pytest.raises(RuntimeError, match="ur_rtde"):
        ur3e_driver.get_connection()
