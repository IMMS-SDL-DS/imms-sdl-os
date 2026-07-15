"""
MOF SDL OS — 일반화된 고체 분주 명령 인터페이스
=================================================
교수님 요청(2026.7): MultiDose 시스템을 OS의 첫 실증(proof of concept)으로 사용.
"어떤 소재를 몇 그램 담아라"는 일반화된 명령 하나를 받으면, 실제 MultiDose
(Universal Robots 로봇팔 + Mettler Toledo XPR 저울)가 그대로 수행하도록 만드는 것이 목표.

역할 분담:
- 로봇팔/저울 저수준 제어: 김연서, 안윤수
- 도징헤드 판 구축: 정윤서
- 이 파일(OS 레이어): 손시영 — 명령 검증 + 로봇 드라이버 호출 + DB 기록을 잇는 다리

핵심 아이디어:
    run_dispense_command("ZrOCl2", 97, "Vial_10mL")
    한 줄만 호출하면 -> Pydantic 검증 -> 로봇 드라이버 실행 -> MongoDB 기록까지 자동.

로봇 드라이버는 이 파일에서 직접 구현하지 않는다. `RobotDriver` 타입으로
"자리"만 정의해두고, 김연서/안윤수가 만드는 실제 제어 함수를 그 자리에
꽂아 넣기만 하면 되도록 설계했다 (지금은 simulated_robot_driver로 대체).

로봇 드라이버 인터페이스 계약 (김연서/안윤수와 맞춰야 할 부분):
    입력: reagent(str), target_mass_mg(float), tolerance_mg(float), vessel(str)
    출력: {"actual_mass_mg": float, "success": bool}
    이 계약이 다르면 김연서/안윤수 실제 구현 시 이 시그니처에 맞춰서 어댑터만
    하나 추가하면 됨 (run_dispense_command 자체는 안 바뀜).
"""

from __future__ import annotations

import random
import uuid
from typing import Callable

from src.database.models import OperationType, Sample, Task, validate_operation_params
from src.database.mongo_client import (
    get_database,
    register_device_if_missing,
    release_device,
    save_sample,
    save_task,
    try_acquire_device,
)

MULTIDOSE_DEVICE_ID = "dev_multidose"

# ── 로봇 드라이버 인터페이스 ─────────────────────────────────────────
RobotDriver = Callable[[str, float, float, str], dict]


def simulated_robot_driver(reagent: str, target_mass_mg: float, tolerance_mg: float, vessel: str) -> dict:
    """
    실제 MultiDose 연동 전 임시 시뮬레이션.
    TODO: 김연서/안윤수의 실제 로봇 제어 함수로 교체 (동일 시그니처 유지).
    """
    actual = target_mass_mg + random.uniform(-tolerance_mg * 0.6, tolerance_mg * 0.6)
    print(f"    [SIM-MultiDose] {reagent} {actual:.2f}mg → {vessel}")
    return {
        "actual_mass_mg": round(actual, 2),
        "success": abs(actual - target_mass_mg) <= tolerance_mg,
    }


# ── 일반화된 명령: "이 소재를 이만큼 담아라" ──────────────────────────
def run_dispense_command(
    reagent: str,
    target_mass_mg: float,
    vessel: str,
    tolerance_mg: float = 5.0,
    experiment_id: str = "multidose_demo",
    robot_driver: RobotDriver = simulated_robot_driver,
    save_to_db: bool = True,
) -> Task:
    """
    범용 고체 분주 명령. 특정 프로토콜(Zr-BTC 등)에 종속되지 않고
    어떤 소재/양/용기 조합이든 그대로 실행된다.

    MultiDose는 여러 사용자/실험이 공유하는 장비이므로, 실행 전 장비가
    idle(비어있음)인지 확인하고 busy로 표시한 뒤 실행한다 (OCTOPUS의
    masking table 개념 — Device.status를 원자적으로 체크+변경).
    이미 다른 Task가 쓰는 중이면 로봇을 호출하지 않고 status="held"로
    반환한다 (충돌 방지).

    예:
        run_dispense_command("ZrOCl2", 97, "Vial_10mL")
        run_dispense_command("BTC", 21, "Vial_5mL", tolerance_mg=2)
    """
    # 1) Pydantic 검증 — src/database/models.py의 OP-01 스키마 그대로 재사용
    params = validate_operation_params(
        OperationType.DISPENSE_SOLID,
        {"reagent": reagent, "mass_mg": target_mass_mg, "tolerance_mg": tolerance_mg, "vessel": vessel},
    )

    step_id = uuid.uuid4().hex[:8]
    task = Task(
        task_id=f"{experiment_id}_dispense_{step_id}",
        experiment_id=experiment_id,
        phase="B",
        step_code=f"DISPENSE_{step_id}",
        operation=OperationType.DISPENSE_SOLID,
        parameters=params.model_dump(),
        device_id=MULTIDOSE_DEVICE_ID,
        status="running",
    )

    # 2) 장비 잠금 시도 (DB 연결 시에만 가능 — save_to_db=False면 잠금 없이 바로 실행)
    db = None
    device_acquired = False
    if save_to_db:
        try:
            db = get_database()
            register_device_if_missing(
                db, MULTIDOSE_DEVICE_ID, name="MultiDose",
                device_type="solid_dispenser", connection="python_api",
            )
            device_acquired = try_acquire_device(db, MULTIDOSE_DEVICE_ID)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 장비 상태 확인 건너뜀 (DB 연결 실패): {e}")
            db = None

        if db is not None and not device_acquired:
            # 다른 Task가 이미 MultiDose를 쓰는 중 — 로봇 호출 없이 대기 상태로 반환
            task.status = "held"
            print(f"    ⏸ MultiDose가 사용 중이라 대기: {task.task_id}")
            save_task(db, task)
            return task

    try:
        # 3) 실제(또는 시뮬레이션) 로봇 실행
        result = robot_driver(reagent, target_mass_mg, tolerance_mg, vessel)
        task.actual_values = result
        task.status = "success" if result["success"] else "failed"

        # 4) 결과를 Sample로도 기록 (ActionGraph Reference Edge: Task -> Sample)
        sample = Sample(
            sample_id=f"{experiment_id}_sample_{step_id}",
            experiment_id=experiment_id,
            sample_code=f"{reagent}_dispensed",
            sample_type="solid",
            produced_by_task_id=task.task_id,
            properties={"actual_mass_mg": result["actual_mass_mg"], "target_mass_mg": target_mass_mg},
        )
        task.output_refs = [sample.sample_id]

        # 5) MongoDB 기록 (연결 실패해도 명령 자체는 계속 진행)
        if save_to_db and db is not None:
            try:
                save_task(db, task)
                save_sample(db, sample)
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ DB 저장 건너뜀 (연결 실패): {e}")
    finally:
        # 6) 성공/실패/예외 여부와 무관하게 장비는 반드시 다시 idle로 되돌린다
        if device_acquired and db is not None:
            release_device(db, MULTIDOSE_DEVICE_ID)

    return task


if __name__ == "__main__":
    # 실증 데모: "ZrOCl2 97mg을 Vial_10mL에 담아라"
    demo_task = run_dispense_command("ZrOCl2", 97, "Vial_10mL", save_to_db=False)
    print(f"\n결과: {demo_task.status}, actual={demo_task.actual_values}")
