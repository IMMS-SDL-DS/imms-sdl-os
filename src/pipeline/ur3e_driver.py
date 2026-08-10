"""
MOF SDL OS — UR3e 로봇팔 드라이버
===================================
action_driver.py의 ActionDriver 규격(Action → dict)에 맞춰,
ur_rtde로 PICK / PLACE / MOUNT / RETRACT를 구현한다.

- rtde_control_interface.h (1순위): 이동 명령(moveL), 안전범위 사전 체크
- rtde_receive_interface.h (2순위): 비상/보호정지 상태 사전 체크, 이동 완료 후
  실제 TCP 위치를 재확인하는 이중 검증
- robotiq_gripper.h (3순위): PICK에서 실제로 물체를 쥐는지, PLACE에서 놓는지
  OBJ 변수(0=이동중,1/2=그립 성공,3=물체 없음)로 확인

설치: pip install ur-rtde robotiq-gripper (또는 해당 바인딩 패키지)

사용법 (Prefect flow 시작 전 한 번 호출):
    from src.pipeline.ur3e_driver import register_ur3e_drivers
    register_ur3e_drivers()   # 이 순간부터 시뮬레이션 대신 실제 로봇이 움직임
"""

from __future__ import annotations

import math
import os
from typing import Optional

from src.database.models import Action, ActionType

# rtde_control / rtde_receive는 실제 로봇 제어 라이브러리라, 설치 안 된 환경(테스트 등)에서도
# import 에러 없이 이 모듈을 불러올 수 있도록 예외 처리한다.
try:
    import rtde_control  # type: ignore
except ImportError:
    rtde_control = None

try:
    import rtde_receive  # type: ignore
except ImportError:
    rtde_receive = None

try:
    import robotiq_gripper  # type: ignore
except ImportError:
    robotiq_gripper = None

UR3E_HOST = os.getenv("UR3E_HOST", "192.168.1.100")  # TODO: 실제 로봇 IP로 교체

# 이동 완료 후 "목표 위치에 진짜 도착했는지" 판정하는 허용 오차 (미터, TCP xyz 기준).
# TODO: 실제 로봇 정밀도/작업 여유공간에 맞춰 조정 필요 — 지금은 5mm로 임시 설정.
POSITION_TOLERANCE_M = 0.005

# ── 로봇팔이 방문하는 위치들의 Cartesian pose [x, y, z, rx, ry, rz] ──────────
# TODO: 실제 로봇 티칭(teach) 후 정확한 좌표로 교체 필요. 지금은 자리표시자(placeholder).
LOCATION_POSES: dict[str, list[float]] = {
    "head_rack": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "vial_rack": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "balance": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "balance_center": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "home": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # RETRACT가 돌아가는 안전 위치
}

GRIPPER_PORT = 63352  # Robotiq 그리퍼는 로봇 컨트롤러 IP의 이 포트로 접속 (매뉴얼 기본값)

# OBJ 변수 의미 (매뉴얼에 명시된 정확한 값 — eObjectStatus enum 대신 이 변수를 직접 읽어서 판정)
OBJ_MOVING = 0
OBJ_STOPPED_OUTER = 1  # 바깥쪽에서 물체 감지 (grip 성공)
OBJ_STOPPED_INNER = 2  # 안쪽에서 물체 감지 (grip 성공)
OBJ_AT_DEST_NO_OBJECT = 3  # 목표 위치 도달, 물체 없음 (release 성공 / grip 실패)

_gripper = None  # RobotiqGripper 싱글턴


def get_gripper(host: str = UR3E_HOST, port: int = GRIPPER_PORT):
    """
    RobotiqGripper 연결을 하나만 유지한다. 최초 연결 시 activate까지 자동으로 해준다
    (활성화 안 된 그리퍼는 move 명령이 안 먹힘).
    """
    global _gripper
    if robotiq_gripper is None:
        raise RuntimeError("robotiq_gripper 모듈이 설치되어 있지 않습니다.")
    if _gripper is None:
        _gripper = robotiq_gripper.RobotiqGripper(host, port)
        _gripper.connect()
        if not _gripper.isActive():
            _gripper.activate()
    return _gripper


def grip() -> dict:
    """
    PICK에서 물체를 쥐는 동작. 그리퍼를 닫고, OBJ 변수로 실제로 뭔가 걸렸는지 확인한다.
    OBJ가 1(바깥쪽 그립) 또는 2(안쪽 그립)면 성공, 3(물체 없이 끝까지 닫힘)이면 실패
    (허공을 쥔 것 — 헤드/바이알이 예상 위치에 없었다는 뜻).
    """
    gripper = get_gripper()
    gripper.close()
    gripper.waitForMotionComplete()
    obj_status = gripper.getVar("OBJ")
    gripped = obj_status in (OBJ_STOPPED_OUTER, OBJ_STOPPED_INNER)
    return {"success": gripped, "object_status": obj_status}


def release() -> dict:
    """
    PLACE에서 물체를 놓는 동작. 그리퍼를 열고, OBJ가 3(물체 없이 정지)인지 확인한다.
    """
    gripper = get_gripper()
    gripper.open()
    gripper.waitForMotionComplete()
    obj_status = gripper.getVar("OBJ")
    released = obj_status == OBJ_AT_DEST_NO_OBJECT
    return {"success": released, "object_status": obj_status}


_connection = None          # RTDEControlInterface 싱글턴 (이동 명령용)
_receive_connection = None  # RTDEReceiveInterface 싱글턴 (상태 읽기용)


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


def get_receive_connection(host: str = UR3E_HOST):
    """RTDEReceiveInterface 연결을 하나만 유지한다 (상태 읽기 전용, moveL과는 별도 연결)."""
    global _receive_connection
    if rtde_receive is None:
        raise RuntimeError("ur_rtde가 설치되어 있지 않습니다. `pip install ur-rtde`로 설치하세요.")
    if _receive_connection is None:
        _receive_connection = rtde_receive.RTDEReceiveInterface(host)
    return _receive_connection


def is_robot_safe() -> bool:
    """
    로봇이 지금 보호정지(protective stop)나 비상정지(emergency stop) 상태가 아닌지 확인.
    움직이기 전에 항상 먼저 체크 — 이미 정지 상태인데 이동 명령을 보내면 의미 없이
    에러만 쌓이거나, 정지 해제 절차 없이 갑자기 움직이려다 문제가 생길 수 있음.
    """
    rtde_r = get_receive_connection()
    return not rtde_r.isProtectiveStopped() and not rtde_r.isEmergencyStopped()


def _pose_reached(target_pose: list[float]) -> bool:
    """
    moveL()이 True를 반환해도, 실제 TCP 위치가 목표에 도달했는지 한 번 더 확인한다
    (이중 검증). 지금은 위치(x,y,z)만 유클리드 거리로 비교 — 방향(rx,ry,rz)까지
    엄밀히 확인하려면 별도 각도 오차 계산이 필요 (TODO, 지금은 위치만으로 충분히 보수적).
    """
    rtde_r = get_receive_connection()
    actual = rtde_r.getActualTCPPose()
    distance = math.dist(actual[:3], target_pose[:3])
    return distance <= POSITION_TOLERANCE_M


def _resolve_pose(location: Optional[str]) -> Optional[list[float]]:
    if location is None:
        return None
    return LOCATION_POSES.get(location)


def _move_to(location: Optional[str], speed: float = 0.25, acceleration: float = 1.2) -> dict:
    """
    지정된 named location으로 moveL 이동. 4단계로 검증한다:
    1) 위치 이름이 등록 안 돼있으면 실패
    2) 로봇이 보호/비상정지 상태면 실패 (is_robot_safe)
    3) 안전 범위(isPoseWithinSafetyLimits) 밖이면 실패 — 실제로 움직이지 않고 미리 막음
    4) moveL 실행 후, 실제 TCP 위치가 목표에 도달했는지 재확인 (_pose_reached)
    """
    pose = _resolve_pose(location)
    if pose is None:
        return {"success": False, "reason": f"unknown location: {location}"}

    if not is_robot_safe():
        return {"success": False, "reason": "robot is in protective/emergency stop"}

    rtde_c = get_connection()

    if not rtde_c.isPoseWithinSafetyLimits(pose):
        return {"success": False, "reason": "pose outside safety limits"}

    ok = rtde_c.moveL(pose, speed=speed, acceleration=acceleration)
    if not ok:
        return {"success": False, "reason": "moveL command failed"}

    if not _pose_reached(pose):
        return {"success": False, "reason": "did not reach target pose within tolerance"}

    return {"success": True}


# ── ActionDriver 구현 (action_driver.py의 ACTION_DRIVERS에 등록될 함수들) ──
def pick_driver(action: Action) -> dict:
    """PICK: source_location으로 이동한 뒤, 그리퍼를 닫아서 실제로 물체를 쥔다."""
    move_result = _move_to(action.source_location)
    if not move_result.get("success"):
        return move_result  # 이동 자체가 실패하면 그리퍼는 시도하지 않음

    grip_result = grip()
    return {"success": grip_result["success"], **grip_result}


def place_driver(action: Action) -> dict:
    """PLACE: dest_location으로 이동한 뒤, 그리퍼를 열어서 물체를 놓는다."""
    move_result = _move_to(action.dest_location)
    if not move_result.get("success"):
        return move_result  # 이동 자체가 실패하면 그리퍼는 시도하지 않음

    release_result = release()
    return {"success": release_result["success"], **release_result}


def mount_driver(action: Action) -> dict:
    """MOUNT: 헤드를 저울에 장착 (dest_location="balance")."""
    return _move_to(action.dest_location)


def retract_driver(action: Action) -> dict:
    """
    RETRACT: 안전 위치("home")로 복귀.
    DOOR_CLOSE(safety_critical)의 전제조건이라 특히 중요 — moveL 반환값만이 아니라
    _pose_reached()로 실제 TCP가 home에 도착했는지까지 확인해야, 로봇팔이 저울
    내부에 남아있는 상태에서 DOOR_CLOSE로 넘어가는 걸 확실히 막을 수 있다.
    """
    return _move_to("home")


def register_ur3e_drivers() -> None:
    """action_driver.py의 ACTION_DRIVERS에 이 파일의 실제 로봇 함수들을 등록한다."""
    from src.pipeline.action_driver import register_action_driver

    register_action_driver(ActionType.PICK, pick_driver)
    register_action_driver(ActionType.PLACE, place_driver)
    register_action_driver(ActionType.MOUNT, mount_driver)
    register_action_driver(ActionType.RETRACT, retract_driver)
