from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE

from src.database.models import (
    OperationType,
    Task,
    is_safely_retryable,
    validate_operation_params,
)
from src.database.mongo_client import get_database, save_task

PROTOCOL_PATH = Path(__file__).resolve().parents[2] / "data" / "protocols" / "solid_dosing_protocol.json"
SOLID_UNIT = "Milligram"


from src.pipeline.solid_dosing.dosing_workflow import DosingWorkflowManager
pipeline = DosingWorkflowManager()


def load_protocol(path: Path = PROTOCOL_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── DB 커넥션: 상시 프로세스 안에서 1회 생성 후 재사용 ─────────────────
@lru_cache(maxsize=1)
def _db():
    return get_database()


# ── 개별 Step 실행 (Unit Operation 1개 = Prefect task 1개) ──────────────
# 기본 retries=0: 물리적 부작용이 있는 오퍼레이션은 재시도하지 않는 것이 안전한 기본값.
# 측정/판독처럼 안전한 오퍼레이션만 _call_execute_step()에서 retries=1을 적용한다.
@task(name="execute_unit_operation", retries=0, cache_policy=NO_CACHE)
def execute_step(
    experiment_id: str,
    phase: str,
    step: dict[str, Any],
    save_to_db: bool = False,
) -> Task:
    logger = get_run_logger()
    operation = OperationType(step["operation"])
    params = validate_operation_params(operation, step["parameters"])

    task_model = Task(
        task_id=f"{experiment_id}_{step['step_code']}",
        experiment_id=experiment_id,
        phase=phase,  # type: ignore[arg-type]
        step_code=step["step_code"],
        operation=operation,
        parameters=params.model_dump(),
        device_id=step.get("device"),
        order_critical=bool(step["parameters"].get("order_critical", False)),
        status="running",
    )

    logger.info(
        f"▶ [{task_model.step_code}] {operation.value} "
        f"(device={task_model.device_id}, required_type={task_model.required_device_type()})"
    )

    if task_model.order_critical:
        logger.warning(f"⚠️ order_critical Step — 순서 강제: {step['parameters']}")

    # TODO: Device gateway 호출로 교체
    print(f"    [REAL] {operation.value} 실행 → output={step.get('output')}")
    pipeline.run(step['parameters']["reagent"], step['parameters']["mass_mg"], SOLID_UNIT)

    task_model.status = "success"
    if step.get("output"):
        task_model.output_refs = [step["output"]]

    if save_to_db:
        save_task(_db(), task_model)

    return task_model


# ── Phase 단위 sub-flow ──────────────────────────────────────────────
def _call_execute_step(experiment_id: str, phase: str, step: dict, save_to_db: bool) -> Task:
    """측정/판독만 retries=1, 물리적 부작용이 있는 오퍼레이션은 retries=0."""
    operation = OperationType(step["operation"])
    if is_safely_retryable(operation):
        return execute_step.with_options(retries=1)(experiment_id, phase, step, save_to_db=save_to_db)
    return execute_step(experiment_id, phase, step, save_to_db=save_to_db)


@flow(name="run_phase")
def run_phase(experiment_id: str, phase_data: dict, save_to_db: bool = False) -> list[Task]:
    logger = get_run_logger()
    phase = phase_data["phase"]
    logger.info(f"=== Phase {phase}: {phase_data['title']} ===")

    # executed: list[Task] = []
    for step in phase_data["steps"]:
        operation = OperationType(step["operation"])

        if operation == OperationType.REPEAT:
            count = step["parameters"]["count"]
            start, end = step["parameters"]["start_step"], step["parameters"]["end_step"]
            logger.info(f"🔁 REPEAT {start}~{end} x{count} ({step['parameters'].get('solvent')})")
            repeat_targets = [
                s for s in phase_data["steps"]
                if s["step_code"] in (start, end) or _step_in_range(s["step_code"], start, end)
            ]
            for i in range(count):
                for target in repeat_targets:
                    if target["operation"] == "REPEAT":
                        continue
                    result = _call_execute_step(
                        experiment_id, phase,
                        {**target, "step_code": f"{target['step_code']}_rep{i+1}"},
                        save_to_db,
                    )
                    # executed.append(result)
            continue

        result = _call_execute_step(experiment_id, phase, step, save_to_db)
        # executed.append(result)

        if result.order_critical and result.status != "success":
            raise RuntimeError(f"order_critical Step 실패: {result.step_code}")

    # return executed


def _step_in_range(step_code: str, start: str, end: str) -> bool:
    """F-2~F-6처럼 같은 prefix의 번호 구간에 속하는지 판별."""
    try:
        prefix = start.split("-")[0]
        s_num = int(start.split("-")[1])
        e_num = int(end.split("-")[1])
        if "-" not in step_code:
            return False
        step_prefix, step_num_str = step_code.split("-")
        if step_prefix != prefix:
            return False
        return s_num <= int(step_num_str) <= e_num
    except (ValueError, IndexError):
        return False


# ── 메인 Flow: 전체 프로토콜(Phase A~G) 실행 ──────────────────────────
@flow(name="Solid-Dosing", log_prints=True)
def solid_dosing_flow(
    experiment_id: Optional[str] = None,
    protocol_path: Optional[str] = None,
    save_to_db: bool = True,
):
    logger = get_run_logger()
    experiment_id = experiment_id or f"solid_dosing_{datetime.now():%Y%m%d_%H%M%S}"
    protocol = load_protocol(Path(protocol_path) if protocol_path else PROTOCOL_PATH)

    print(f"{'='*60}")
    print(f"  Experiment: {experiment_id}")
    print(f"{'='*60}")

    if save_to_db:
        try:
            _db()["experiment"].update_one(
                {"experiment_id": experiment_id},
                {"$set": {
                    "experiment_id": experiment_id,
                    "name": protocol["protocol_name"],
                    "protocol_version": protocol["protocol_version"],
                    "target_material": protocol["target_material"],
                    "reagents": protocol["reagents"],
                    "phase_sequence": [p["phase"] for p in protocol["phases"]],
                    "status": "running",
                    "started_at": datetime.now(),
                    "notes": protocol["global_notes"],
                }},
                upsert=True,
            )
        except Exception as e:  # noqa: BLE001 — DB 실패해도 시뮬레이션은 계속
            logger.warning(f"⚠️ MongoDB 저장 건너뜀 (연결 실패): {e}")
            _db.cache_clear()
            save_to_db = False

    try:
        for phase_data in protocol["phases"]:
            run_phase(experiment_id, phase_data, save_to_db=save_to_db)
    except Exception:
        if save_to_db:
            _db()["experiment"].update_one(
                {"experiment_id": experiment_id},
                {"$set": {"status": "failed", "ended_at": datetime.now()}},
            )
        raise

    if save_to_db:
        _db()["experiment"].update_one(
            {"experiment_id": experiment_id},
            {"$set": {"status": "completed", "ended_at": datetime.now()}},
        )

    print("Solid Dosing 실행 완료")