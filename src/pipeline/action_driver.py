"""
MOF SDL OS — Action 레벨 로봇 드라이버 인터페이스
===================================================
"로봇 제어 코드가 어떤 형태인지 몰라서 연동을 못 한다"는 문제를 뒤집는 방식:
질문으로 알아내는 대신, 우리가 정확한 "규격"을 먼저 정의해서 로봇 제어팀에게
"이 규격에 맞는 함수만 만들어주세요"라고 요청한다.

사용법 (로봇 제어팀이 할 일):
    아래 ActionDriver 시그니처에 맞는 함수를 ActionType별로 하나씩 구현해서
    ACTION_DRIVERS 딕셔너리에 등록하면 끝. 함수 내부 구현(UR3e RTDE 호출이든
    URScript든)은 뭐든 상관없음 — 입력/출력 형태만 아래 규격을 따르면 됨.

    예:
        def pick_driver(action: Action) -> dict:
            # 실제 UR3e 제어 코드 (RTDE, URScript 등 뭐든)
            robot.movej(...)
            return {"success": True}

        ACTION_DRIVERS[ActionType.PICK] = pick_driver
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from src.database.models import Action, ActionType
from src.hardware.balance_mtsics import (
    BalanceError,
    BalanceOverloadError,
    BalanceTimeoutError,
    MTSICSBalance,
)

# ─────────────────────────────────────────────────────────────
# 규격: ActionDriver
# ─────────────────────────────────────────────────────────────
# 입력: Action 객체 하나 (object_ref, source_location, dest_location, parameters 등
#       실행에 필요한 정보가 다 들어있음)
# 출력: 최소 {"success": bool}을 포함한 dict.
#       DOSE/STABILIZE처럼 추가로 측정값이 필요한 Action은 그 값도 같이 넣어서 반환.
#         - DOSE       -> {"success": bool, "actual_mass_mg": float}
#         - STABILIZE  -> {"success": bool, "is_stable": bool, "final_reading_mg": float}
#         - 나머지     -> {"success": bool} 만 있어도 충분
ActionDriver = Callable[[Action], dict]


# ── 로봇 제어팀이 채워 넣을 자리. 지금은 전부 시뮬레이션 함수로 등록되어 있음. ──
def _simulated_driver(action: Action) -> dict:
    """실제 함수가 등록되기 전까지 쓰는 기본 시뮬레이션."""
    print(f"    [SIM-Action] {action.action_type.value} (#{action.sequence_index})")
    result = {"success": True}
    if action.action_type == ActionType.DOSE:
        result["actual_mass_mg"] = 0.0  # 실제 연동 전까지는 의미 없는 값
    if action.action_type == ActionType.STABILIZE:
        result["is_stable"] = True
        result["final_reading_mg"] = 0.0
    return result


ACTION_DRIVERS: dict[ActionType, ActionDriver] = {
    action_type: _simulated_driver for action_type in ActionType
}


def register_action_driver(action_type: ActionType, driver: ActionDriver) -> None:
    """로봇 제어팀의 실제 함수를 등록. 예: register_action_driver(ActionType.PICK, pick_driver)"""
    ACTION_DRIVERS[action_type] = driver


# ─────────────────────────────────────────────────────────────
# 실제 드라이버 — XPR 저울 (MT-SICS) 대응 Action들
# STABILIZE / DOOR_OPEN / DOOR_CLOSE는 이 매뉴얼만으로 완전 구현 가능.
# PICK / PLACE / RETRACT / MOUNT는 여전히 UR3e 로봇팔 문서 대기 중 (시뮬레이션 유지).
# ─────────────────────────────────────────────────────────────

_balance: Optional[MTSICSBalance] = None


def _get_balance() -> MTSICSBalance:
    """
    저울 커넥션 lazy 초기화(모듈 import 시점엔 하드웨어가 없어도 되도록).
    device_id별 다중 저울을 쓰게 되면 이 함수를 dict[device_id, MTSICSBalance]로 확장.
    """
    global _balance
    if _balance is None:
        try:
            _balance = MTSICSBalance()  # .env의 BALANCE_SERIAL_PORT 사용
        except KeyError as e:
            raise BalanceError(f".env에 {e} 설정 안 됨 (BALANCE_SERIAL_PORT 필요)") from e
        except Exception as e:  # serial.SerialException 등 pyserial 쪽 예외 포함
            raise BalanceError(f"저울 연결 실패: {e}") from e
    return _balance


def stabilize_driver(action: Action) -> dict:
    """
    STABILIZE — models.py의 StabilizeParams(stability_threshold_mg, max_wait_sec)를
    그대로 사용. MT-SICS의 S 명령 자체가 "안정될 때까지 대기 후 응답"이므로
    stability_threshold_mg는 별도 계산 없이 저울의 자체 안정 판정에 위임하고,
    max_wait_sec만 우리 쪽 read_stable() 타임아웃으로 넘긴다.
    """
    max_wait_sec = action.parameters.get("max_wait_sec", 30.0)
    try:
        reading = _get_balance().read_stable(timeout_sec=max_wait_sec)
        return {"success": True, "is_stable": reading.is_stable, "final_reading_mg": reading.value_mg}
    except (BalanceTimeoutError, BalanceOverloadError, BalanceError):
        return {"success": False, "is_stable": False, "final_reading_mg": None}


def door_open_driver(action: Action) -> dict:
    """DOOR_OPEN — WS 명령. 매뉴얼 p.80."""
    try:
        _get_balance().open_door()
        return {"success": True}
    except BalanceError:
        return {"success": False}


def door_close_driver(action: Action) -> dict:
    """DOOR_CLOSE — WS 0. safety_critical Action이라 execute_action_sequence()가
    이전 RETRACT 성공 여부를 먼저 검증한 뒤에만 이 드라이버를 호출한다."""
    try:
        _get_balance().close_door()
        return {"success": True}
    except BalanceError:
        return {"success": False}


def dose_trigger(action: Action) -> None:
    """
    ⚠️ 플레이스홀더 — MultiDose 헤드에서 실제로 분체를 방출시키는 트리거.
    MT-SICS 저울 매뉴얼 범위 밖 (도징헤드 전용 명령/API가 별도로 필요,
    아직 확보 못함 — UR3e 로봇팔 문서와 같은 카테고리의 블로커).
    지금은 아무 것도 안 하고 통과시켜서, 저울 모니터링 로직만 먼저 검증 가능하게 함.
    """
    print(f"    [TODO] 도징헤드 방출 트리거 미구현 (object_ref={action.object_ref})")


def dose_driver(action: Action) -> dict:
    """
    DOSE — 목표 중량은 Task.build_solid_dosing_actions()가 미리 심어둔
    action.parameters["target_mass_mg"] / ["tolerance_mg"]를 사용
    (models.py 수정 사항 참고 — 이게 없으면 이 드라이버는 동작 안 함).

    흐름: tare -> 방출 트리거(현재 미구현) -> 목표치 도달까지 SI로 폴링.
    tolerance 충족 여부 최종 판단은 여기서 하지 않고 actual_mass_mg만 반환 —
    WITHIN_TOLERANCE/CORRECTION_DOSE/FAIL_VIAL 판단은 models.decide_tolerance()가
    Task 레벨에서 하도록 역할을 분리한다 (중복 로직 방지).
    """
    target_mass_mg = action.parameters.get("target_mass_mg")
    if target_mass_mg is None:
        return {"success": False, "actual_mass_mg": None}

    max_wait_sec = action.parameters.get("dose_max_wait_sec", 60.0)
    poll_interval_sec = 0.5

    try:
        balance = _get_balance()
        balance.tare_immediately()
        dose_trigger(action)

        deadline = time.time() + max_wait_sec
        last_reading = 0.0
        while time.time() < deadline:
            reading = balance.read_immediate()
            last_reading = reading.value_mg
            if reading.is_stable and last_reading >= target_mass_mg:
                break
            time.sleep(poll_interval_sec)

        return {"success": True, "actual_mass_mg": last_reading}
    except BalanceError:
        return {"success": False, "actual_mass_mg": None}


register_action_driver(ActionType.STABILIZE, stabilize_driver)
register_action_driver(ActionType.DOOR_OPEN, door_open_driver)
register_action_driver(ActionType.DOOR_CLOSE, door_close_driver)
register_action_driver(ActionType.DOSE, dose_driver)


def execute_action(action: Action) -> dict:
    """등록된 드라이버로 Action 하나를 실행하고 결과를 반환."""
    driver = ACTION_DRIVERS[action.action_type]
    return driver(action)


def execute_action_sequence(actions: list[Action]) -> list[Action]:
    """
    Action 리스트를 순서대로 실행. safety_critical Action은 실행 전
    이전 Action이 success인지 확인 (models.py의 validate 로직과 동일 원칙).
    """
    for i, action in enumerate(actions):
        if action.safety_critical and i > 0 and actions[i - 1].status != "success":
            action.status = "failed"
            raise ValueError(
                f"안전 순서 위반: {action.action_type}(#{action.sequence_index})은 "
                f"이전 Action이 success여야 실행 가능합니다."
            )

        action.status = "running"
        result = execute_action(action)
        action.status = "success" if result.get("success") else "failed"

        if action.action_type == ActionType.DOSE and "actual_mass_mg" in result:
            action.parameters["actual_mass_mg"] = result["actual_mass_mg"]
        if action.action_type == ActionType.STABILIZE:
            action.parameters["is_stable"] = result.get("is_stable")
            action.parameters["final_reading_mg"] = result.get("final_reading_mg")

    return actions


if __name__ == "__main__":
    from src.database.models import OperationType, Task

    task = Task(
        task_id="demo_dispense1", experiment_id="demo", phase="B", step_code="B-1",
        operation=OperationType.DISPENSE_SOLID,
        parameters={"reagent": "ZrOCl2", "mass_mg": 97, "vessel": "V1"},
        device_id="dev_multidose",
    )
    actions = task.build_solid_dosing_actions()
    execute_action_sequence(actions)
    print(f"\n{len(actions)}개 Action 실행 완료")
    print("   PICK/PLACE/RETRACT/MOUNT: 시뮬레이션 (UR3e 문서 대기 중)")
    print("   STABILIZE/DOOR_OPEN/DOOR_CLOSE/DOSE: 실제 MT-SICS 드라이버")
    print("   (하드웨어 미연결 환경이면 BalanceError로 success=False 처리됨 — 정상 동작)")
