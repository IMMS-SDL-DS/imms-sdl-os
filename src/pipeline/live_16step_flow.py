"""
SDL OS — 16-Step Solid Dosing, 실제 Prefect + MongoDB 연동 버전
====================================================================
기존 demo_16step.py는 그냥 파이썬 함수 호출이라 Prefect 대시보드나
MongoDB Atlas에 아무 흔적이 안 남았음. 이 스크립트는 그 간극을 메움:

  1) @flow / @task 데코레이터로 감싸서 → Prefect UI에 실행 기록이 보임
  2) 실행 끝난 Task(+16개 Action 전부 포함)를 MongoDB에 실제로 저장

실행 전 준비:
  1) 터미널 1: prefect server start        (Prefect UI: http://localhost:4200)
  2) .env 파일에 MONGODB_URI, MONGODB_DB_NAME 설정 (없으면 DB 저장만 건너뜀)
  3) 터미널 2: python3 live_16step_flow.py

실행 후 확인:
  - Prefect UI (localhost:4200) → Flow Runs에 "solid-dosing-16step" 실행 기록 확인
  - MongoDB Atlas → Browse Collections → task 컬렉션 →
    task_id="live_dispense_<시각>" 문서 안에 actions 16개가 그대로 저장돼있는지 확인
"""
from __future__ import annotations

from datetime import datetime
from prefect import flow, task, get_run_logger

from src.database.models import OperationType, Task, ActionType
from src.database.mongo_client import get_database, save_task
from src.pipeline.action_driver import execute_action_sequence, ACTION_DRIVERS


@task(name="build_16_actions")
def build_actions_task(task_obj: Task) -> Task:
    """Task 하나 → 16개 Action으로 분해 (Prefect task로 감싸서 UI에 노출)"""
    logger = get_run_logger()
    actions = task_obj.build_solid_dosing_actions()
    logger.info(f"16개 Action 생성 완료 (safety_critical: "
                f"{[a.sequence_index for a in actions if a.safety_critical]}번)")
    return task_obj


@task(name="execute_16_actions", retries=0)
def execute_actions_task(task_obj: Task) -> Task:
    """16개 Action을 순서대로 실행 (물리적 동작 포함 → 재시도 안 함)"""
    logger = get_run_logger()
    execute_action_sequence(task_obj.actions)
    n_success = sum(1 for a in task_obj.actions if a.status == "success")
    n_failed = sum(1 for a in task_obj.actions if a.status == "failed")
    logger.info(f"실행 완료: 성공 {n_success}개 / 실패 {n_failed}개 (총 16개)")
    task_obj.status = "success" if n_failed == 0 else "failed"
    return task_obj


@task(name="save_to_mongodb")
def save_task_to_db(task_obj: Task) -> bool:
    """MongoDB에 Task + 16개 Action 전체를 저장 (.env 없으면 건너뜀)"""
    logger = get_run_logger()
    try:
        db = get_database()
    except Exception as e:
        logger.warning(f"MongoDB 연결 실패 — 저장 건너뜀 (.env 확인 필요): {e}")
        return False
    save_task(db, task_obj)
    logger.info(f"MongoDB 저장 완료 — task_id={task_obj.task_id}")
    return True


@flow(name="solid-dosing-16step")
def solid_dosing_16step_flow(force_retract_fail: bool = False) -> Task:
    """
    고체 분주(Solid Dosing) 16-Step 전체 플로우.
    force_retract_fail=True로 주면 안전장치(DOOR_CLOSE 차단) 시연 가능.
    """
    logger = get_run_logger()
    task_id = f"live_dispense_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    task_obj = Task(
        task_id=task_id, experiment_id="exp_zrbtc_live", phase="B", step_code="B-1",
        operation=OperationType.DISPENSE_SOLID,
        parameters={"reagent": "ZrOCl2", "mass_mg": 97, "vessel": "V1"},
        device_id="dev_multidose",
    )

    task_obj = build_actions_task(task_obj)

    original_retract = None
    if force_retract_fail:
        logger.warning("⚠ 안전장치 시연 모드 — RETRACT 강제 실패시킴")
        original_retract = ACTION_DRIVERS[ActionType.RETRACT]
        ACTION_DRIVERS[ActionType.RETRACT] = lambda action: {"success": False}

    try:
        task_obj = execute_actions_task(task_obj)
    except ValueError as e:
        logger.error(f"안전 순서 위반으로 실행 중단: {e}")
        task_obj.status = "failed"
    finally:
        if original_retract is not None:
            ACTION_DRIVERS[ActionType.RETRACT] = original_retract

    save_task_to_db(task_obj)
    return task_obj


if __name__ == "__main__":
    print("=" * 60)
    print("1) 정상 실행")
    print("=" * 60)
    solid_dosing_16step_flow(force_retract_fail=False)

    print("\n" + "=" * 60)
    print("2) 안전장치 시연 (RETRACT 강제 실패)")
    print("=" * 60)
    solid_dosing_16step_flow(force_retract_fail=True)