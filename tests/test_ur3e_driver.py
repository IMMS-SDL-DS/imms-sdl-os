"""
src/pipeline/ur3e_driver.py 테스트.
실제 UR3e 로봇/ur_rtde 라이브러리 없이, get_connection()/get_receive_connection()을
가짜 객체로 대체해서 검증한다.
"""

import pytest

from src.database.models import Action, ActionType
from src.pipeline import ur3e_driver


class FakeRTDE:
    """
    RTDEControlInterface + RTDEReceiveInterface를 하나로 합친 가짜 객체.
    실제로는 별도 클래스지만, 테스트에서는 한 인스턴스가 둘 다 흉내내도 충분하다.
    """

    def __init__(
        self,
        within_limits: bool = True,
        move_success: bool = True,
        protective_stopped: bool = False,
        emergency_stopped: bool = False,
        pose_reached: bool = True,
    ):
        self.within_limits = within_limits
        self.move_success = move_success
        self.protective_stopped = protective_stopped
        self.emergency_stopped = emergency_stopped
        self.pose_reached = pose_reached
        self.moveL_calls: list[list[float]] = []
        self._last_target_pose: list[float] | None = None

    # RTDEControlInterface 쪽
    def isPoseWithinSafetyLimits(self, pose):
        return self.within_limits

    def moveL(self, pose, speed, acceleration):
        self.moveL_calls.append(pose)
        self._last_target_pose = pose
        return self.move_success

    # RTDEReceiveInterface 쪽
    def isProtectiveStopped(self):
        return self.protective_stopped

    def isEmergencyStopped(self):
        return self.emergency_stopped

    def getActualTCPPose(self):
        if self.pose_reached and self._last_target_pose is not None:
            return self._last_target_pose
        return [999.0, 999.0, 999.0, 0.0, 0.0, 0.0]  # 목표와 멀리 떨어진 값


def _action(action_type, **kwargs) -> Action:
    return Action(
        action_id="a1", parent_task_id="t1", sequence_index=1,
        action_type=action_type, **kwargs,
    )


def _patch(monkeypatch, fake: FakeRTDE):
    monkeypatch.setattr(ur3e_driver, "get_connection", lambda: fake)
    monkeypatch.setattr(ur3e_driver, "get_receive_connection", lambda: fake)


# ── 정상 동작 ─────────────────────────────────────────────────────────
def test_pick_driver_moves_to_source_location(monkeypatch):
    fake = FakeRTDE()
    _patch(monkeypatch, fake)

    result = ur3e_driver.pick_driver(_action(ActionType.PICK, source_location="head_rack"))

    assert result["success"] is True
    assert len(fake.moveL_calls) == 1


def test_place_driver_moves_to_dest_location(monkeypatch):
    fake = FakeRTDE()
    _patch(monkeypatch, fake)

    result = ur3e_driver.place_driver(_action(ActionType.PLACE, dest_location="vial_rack"))

    assert result["success"] is True
    assert fake.moveL_calls[0] == ur3e_driver.LOCATION_POSES["vial_rack"]


def test_retract_driver_always_targets_home(monkeypatch):
    fake = FakeRTDE()
    _patch(monkeypatch, fake)

    ur3e_driver.retract_driver(_action(ActionType.RETRACT))

    assert fake.moveL_calls[0] == ur3e_driver.LOCATION_POSES["home"]


def test_mount_driver_moves_to_balance(monkeypatch):
    fake = FakeRTDE()
    _patch(monkeypatch, fake)

    result = ur3e_driver.mount_driver(_action(ActionType.MOUNT, dest_location="balance"))

    assert result["success"] is True


# ── 실패 케이스 ───────────────────────────────────────────────────────
def test_driver_fails_when_location_unknown(monkeypatch):
    fake = FakeRTDE()
    _patch(monkeypatch, fake)

    result = ur3e_driver.place_driver(_action(ActionType.PLACE, dest_location="어딘가_없는_곳"))

    assert result["success"] is False
    assert len(fake.moveL_calls) == 0  # 안 움직여야 함


def test_move_fails_when_outside_safety_limits(monkeypatch):
    fake = FakeRTDE(within_limits=False)
    _patch(monkeypatch, fake)

    result = ur3e_driver.retract_driver(_action(ActionType.RETRACT))

    assert result["success"] is False
    assert "safety" in result["reason"]
    assert len(fake.moveL_calls) == 0


def test_move_fails_when_robot_is_protective_stopped(monkeypatch):
    """비상/보호정지 상태면, moveL 자체를 호출하지 않고 미리 막아야 함."""
    fake = FakeRTDE(protective_stopped=True)
    _patch(monkeypatch, fake)

    result = ur3e_driver.pick_driver(_action(ActionType.PICK, source_location="head_rack"))

    assert result["success"] is False
    assert "protective" in result["reason"] or "emergency" in result["reason"]
    assert len(fake.moveL_calls) == 0


def test_move_fails_when_robot_is_emergency_stopped(monkeypatch):
    fake = FakeRTDE(emergency_stopped=True)
    _patch(monkeypatch, fake)

    result = ur3e_driver.retract_driver(_action(ActionType.RETRACT))

    assert result["success"] is False
    assert len(fake.moveL_calls) == 0


def test_move_fails_when_movel_returns_false(monkeypatch):
    fake = FakeRTDE(move_success=False)
    _patch(monkeypatch, fake)

    result = ur3e_driver.pick_driver(_action(ActionType.PICK, source_location="vial_rack"))

    assert result["success"] is False


def test_move_fails_when_actual_position_does_not_match_target(monkeypatch):
    """moveL은 True를 반환했지만, 실제 위치가 목표와 다르면 실패로 처리해야 함 (이중 검증)."""
    fake = FakeRTDE(move_success=True, pose_reached=False)
    _patch(monkeypatch, fake)

    result = ur3e_driver.retract_driver(_action(ActionType.RETRACT))

    assert result["success"] is False
    assert "tolerance" in result["reason"] or "reach" in result["reason"]


def test_is_robot_safe_reflects_stop_states(monkeypatch):
    fake_ok = FakeRTDE()
    monkeypatch.setattr(ur3e_driver, "get_receive_connection", lambda: fake_ok)
    assert ur3e_driver.is_robot_safe() is True

    fake_stopped = FakeRTDE(protective_stopped=True)
    monkeypatch.setattr(ur3e_driver, "get_receive_connection", lambda: fake_stopped)
    assert ur3e_driver.is_robot_safe() is False


# ── 등록 & 예외 처리 ─────────────────────────────────────────────────
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
        for t in [ActionType.PICK, ActionType.PLACE, ActionType.MOUNT, ActionType.RETRACT]:
            register_action_driver(t, _simulated_driver)


def test_get_connection_raises_clear_error_without_ur_rtde_installed(monkeypatch):
    monkeypatch.setattr(ur3e_driver, "rtde_control", None)
    monkeypatch.setattr(ur3e_driver, "_connection", None)

    with pytest.raises(RuntimeError, match="ur_rtde"):
        ur3e_driver.get_connection()


def test_get_receive_connection_raises_clear_error_without_ur_rtde_installed(monkeypatch):
    monkeypatch.setattr(ur3e_driver, "rtde_receive", None)
    monkeypatch.setattr(ur3e_driver, "_receive_connection", None)

    with pytest.raises(RuntimeError, match="ur_rtde"):
        ur3e_driver.get_receive_connection()
