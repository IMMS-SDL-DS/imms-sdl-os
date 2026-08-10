"""
MOF SDL OS — UR3e 로봇팔 드라이버
===================================
action_driver.py의 ActionDriver 규격(Action → dict)에 맞춰,
ur_rtde의 RTDEControlInterface(rtde_control_interface.h, 1순위 문서)로
PICK / PLACE / MOUNT / RETRACT를 구현한다.

설치: pip install ur-rtde

아직 못 채운 부분 (다음 문서 필요):
- 그리퍼 열기/닫기 실제 동작 — robotiq_gripper.h(3순위) 확보 후 pick_driver/place_driver에 추가
- moveL 완료 후 더 정밀한 상태 확인 — rtde_receive_interface.h(2순위) 확보 후 보강

사용법 (Prefect flow 시작 전 한 번 호출):
    from src.pipeline.ur3e_driver import register_ur3e_drivers
    register_ur3e_drivers()   # 이 순간부터 시뮬레이션 대신 실제 로봇이 움직임
"""

from __future__ import annotations

import os
from typing import Optional

from src.database.models import Action, ActionType

# rtde_control은 실제 로봇 제어 라이브러리라, 설치 안 된 환경(테스트 등)에서도
# import 에러 없이 이 모듈을 불러올 수 있도록 예외 처리한다.
try:
    import rtde_control  # type: ignore
except ImportError:
    rtde_control = None

UR3E_HOST = os.getenv("UR3E_HOST", "192.168.1.100")  # TODO: 실제 로봇 IP로 교체

# ── 로봇팔이 방문하는 위치들의 Cartesian pose [x, y, z, rx, ry, rz] ──────────
# TODO: 실제 로봇 티칭(teach) 후 정확한 좌표로 교체 필요. 지금은 자리표시자(placeholder).
LOCATION_POSES: dict[str, list[float]] = {
    "head_rack": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "vial_rack": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "balance": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "balance_center": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "home": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # RETRACT가 돌아가는 안전 위치
}

_connection = None  # RTDEControlInterface 싱글턴


def get_connection(host: str = UR3E_HOST):
    """
    RTDEControlInterface 연결을 하나만 유지한다 (매 Action마다 새로 연결하면 느림/불안정).
    테스트에서는 monkeypatch로 이 함수 자체를 가짜 객체로 대체해서 실제 로봇 없이 검증한다.
    """
    global _connection
    if rtde_control is None:
        raise RuntimeError("ur_rtde가 설치되어 있지 않습니다. `pip install ur-rtde`로 설치하세요.")
    if _connection is None:
        _connection = rtde_control.RTDEControlInterface(host)
    return _connection


def _resolve_pose(location: Optional[str]) -> Optional[list[float]]:
    if location is None:
        return None
    return LOCATION_POSES.get(location)


def _move_to(location: Optional[str], speed: float = 0.25, acceleration: float = 1.2) -> dict:
    """
    지정된 named location으로 moveL 이동.
    1) 위치 이름이 등록 안 돼있으면 실패
    2) 안전 범위(isPoseWithinSafetyLimits) 밖이면 실패 — 실제로 움직이지 않고 미리 막음
    3) moveL 실행 결과를 그대로 success로 반환
    """
    pose = _resolve_pose(location)
    if pose is None:
        return {"success": False, "reason": f"unknown location: {location}"}

    rtde_c = get_connection()

    if not rtde_c.isPoseWithinSafetyLimits(pose):
        return {"success": False, "reason": "pose outside safety limits"}

    ok = rtde_c.moveL(pose, speed=speed, acceleration=acceleration)
    return {"success": bool(ok)}


# ── ActionDriver 구현 (action_driver.py의 ACTION_DRIVERS에 등록될 함수들) ──
def pick_driver(action: Action) -> dict:
    """PICK: source_location으로 이동. 그리퍼 닫기는 TODO (robotiq_gripper.h 필요)."""
    result = _move_to(action.source_location)
    # TODO: gripper.close() — Robotiq 그리퍼 API 문서 확보 후 추가
    return result


def place_driver(action: Action) -> dict:
    """PLACE: dest_location으로 이동. 그리퍼 열기는 TODO (robotiq_gripper.h 필요)."""
    result = _move_to(action.dest_location)
    # TODO: gripper.open() — Robotiq 그리퍼 API 문서 확보 후 추가
    return result


def mount_driver(action: Action) -> dict:
    """MOUNT: 헤드를 저울에 장착 (dest_location="balance")."""
    return _move_to(action.dest_location)


def retract_driver(action: Action) -> dict:
    """
    RETRACT: 안전 위치("home")로 복귀.
    DOOR_CLOSE(safety_critical)의 전제조건이라 특히 중요 — 실패하면 절대
    다음 Action(DOOR_CLOSE)이 진행되면 안 됨 (execute_action_sequence가 이미 이걸 검증함).
    """
    return _move_to("home")


def register_ur3e_drivers() -> None:
    """action_driver.py의 ACTION_DRIVERS에 이 파일의 실제 로봇 함수들을 등록한다."""
    from src.pipeline.action_driver import register_action_driver

    register_action_driver(ActionType.PICK, pick_driver)
    register_action_driver(ActionType.PLACE, place_driver)
    register_action_driver(ActionType.MOUNT, mount_driver)
    register_action_driver(ActionType.RETRACT, retract_driver)
