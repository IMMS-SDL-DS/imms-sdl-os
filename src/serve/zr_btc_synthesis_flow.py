"""
MOF SDL OS — Zr-BTC 합성 프로토콜 Prefect Flow (상시 서버 모드)
================================================================
실험팀 제공 프로토콜(data/protocols/zr_btc_mof_protocol.json)을 읽어
Phase 단위 Prefect sub-flow + Step 단위 Prefect task로 실행한다.

실행 방식
- 상시 서버:  `prefect server start` 실행 후 이 파일을 실행하면 deployment로 등록되어 대기.
             웹 UI(http://127.0.0.1:4200) → Deployments → Run 으로 실행.
- 1회 실행:   `python -m <이 모듈> --once`

핵심 설계 포인트 (참고: OCTOPUS 논문, ActionGraph 프레임워크)
1. 각 Step은 src.database.models.Task로 검증된 뒤 실행된다.
2. order_critical=True인 Step은 실패 시 즉시 flow 전체를 중단시킨다.
3. REPEAT(OP-16)는 start_step~end_step 구간을 count만큼 반복 실행한다.
4. Device 공유 충돌 방지 훅은 이후 Prefect global concurrency limit으로 구현 예정.

서버 모드 변경점
- DB 핸들은 task 인자로 넘기지 않는다(직렬화 불가). save_to_db 플래그만 넘기고
  프로세스 내에서 커넥션을 1회 생성해 재사용한다.
- 파라미터는 모두 JSON 직렬화 가능한 타입만 사용한다(웹 UI 입력 폼 대응).

TODO(실장비 연동 전까지는 전부 시뮬레이션):
- execute_step() 안의 [SIM] print문을 Device gateway 호출로 교체
"""

from __future__ import annotations

import argparse
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

PROTOCOL_PATH = Path(__file__).resolve().parents[2] / "data" / "protocols" / "zr_btc_mof_protocol.json"
DEPLOYMENT_NAME = "zr-btc-sim"


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
    print(f"    [SIM] {operation.value} 실행 → output={step.get('output')}")

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

    executed: list[Task] = []
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
                    executed.append(result)
            continue

        result = _call_execute_step(experiment_id, phase, step, save_to_db)
        executed.append(result)

        if result.order_critical and result.status != "success":
            raise RuntimeError(f"order_critical Step 실패: {result.step_code}")

    return executed


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
@flow(name="Zr-BTC-MOF-Synthesis", log_prints=True)
def zr_btc_synthesis_flow(
    experiment_id: Optional[str] = None,
    protocol_path: Optional[str] = None,
    save_to_db: bool = True,
):
    logger = get_run_logger()
    experiment_id = experiment_id or f"exp_zrbtc_{datetime.now():%Y%m%d_%H%M%S}"
    protocol = load_protocol(Path(protocol_path) if protocol_path else PROTOCOL_PATH)

    print(f"\n{'='*60}")
    print(f"  {protocol['protocol_name']} ({protocol['protocol_version']})")
    print(f"  Experiment: {experiment_id} | Target: {protocol['target_material']}")
    print(f"{'='*60}\n")

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

    all_tasks: list[Task] = []
    try:
        for phase_data in protocol["phases"]:
            all_tasks.extend(run_phase(experiment_id, phase_data, save_to_db=save_to_db))
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

    print(f"\n✅ 전체 {len(all_tasks)}개 Task 실행 완료")
    print(f"⚠️  Notes: {len(protocol['global_notes'])}건 (docs/db_schema.md 참고)")
    print(f"💾 DB 저장: {'완료' if save_to_db else '건너뜀 (시뮬레이션 전용)'}")

    return all_tasks


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--once", action="store_true", help="서버 등록 없이 1회 실행")
#     args = parser.parse_args()

#     if args.once:
#         zr_btc_synthesis_flow()
#     else:
#         # deployment 등록 + 상시 대기 (웹 UI에서 Run 시 이 프로세스가 실행)
#         zr_btc_synthesis_flow.serve(
#             name=DEPLOYMENT_NAME,
#             tags=["sdl", "zr-btc", "sim"],
#             description="Zr-BTC MOF 합성 프로토콜 (시뮬레이션)",
#         )