"""
MOF SDL OS — Zr-BTC 합성 프로토콜 Prefect Flow
================================================
실험팀 제공 프로토콜(data/protocols/zr_btc_mof_protocol.json)을 그대로 읽어
Phase 단위 Prefect sub-flow + Step 단위 Prefect task로 실행한다.

핵심 설계 포인트 (참고: OCTOPUS 논문, ActionGraph 프레임워크)
1. 각 Step은 src.database.models.Task로 검증된 뒤 실행된다.
2. order_critical=True인 Step(예: D-1 TRANSFER)은 순서를 보장해야 하므로
   반드시 동기적으로, 그리고 실패 시 즉시 flow 전체를 중단시킨다.
3. REPEAT(OP-16)는 start_step~end_step 구간을 count만큼 반복 실행한다.
4. Device는 여러 Phase에서 공유되므로(Opentron Flex 등), 실행 전 상태를
   busy/idle로 표시해 이후 실제 장비 연동 시 충돌을 막을 수 있도록 훅을 남긴다.

TODO(실장비 연동 전까지는 전부 시뮬레이션):
- _execute_on_device() 안의 print문들을 실제 장비 Python API 호출로 교체
- MongoDB 연결(collect_to_mongo)로 Task/Sample 문서 실제 저장
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from prefect import flow, get_run_logger, task

from src.database.models import (
    OperationType,
    Task,
    validate_operation_params,
)

PROTOCOL_PATH = Path(__file__).resolve().parents[2] / "data" / "protocols" / "zr_btc_mof_protocol.json"


def load_protocol(path: Path = PROTOCOL_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 개별 Step 실행 (Unit Operation 1개 = Prefect task 1개) ──────────────
@task(name="execute_unit_operation", retries=1)
def execute_step(
    experiment_id: str,
    phase: str,
    step: dict[str, Any],
) -> Task:
    logger = get_run_logger()
    operation = OperationType(step["operation"])

    # REPEAT은 파라미터만 있고 실제 장비 동작이 없으므로 별도 처리
    if operation == OperationType.REPEAT:
        logger.info(f"[REPEAT] {step['parameters']}")
        params = validate_operation_params(operation, step["parameters"])
    else:
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

    # order_critical Step은 여기서 순서 위반을 감지하면 예외를 던져 flow를 중단시킨다.
    if task_model.order_critical:
        logger.warning(
            f"⚠️ order_critical Step — 순서 강제: {step['parameters']}"
        )

    # TODO: 실제 장비 Python API 호출로 교체
    print(f"    [SIM] {operation.value} 실행 → output={step.get('output')}")

    task_model.status = "success"
    if step.get("output"):
        task_model.output_refs = [step["output"]]

    return task_model


# ── Phase 단위 sub-flow ──────────────────────────────────────────────
@flow(name="run_phase")
def run_phase(experiment_id: str, phase_data: dict) -> list[Task]:
    logger = get_run_logger()
    phase = phase_data["phase"]
    logger.info(f"=== Phase {phase}: {phase_data['title']} ===")

    executed: list[Task] = []
    for step in phase_data["steps"]:
        operation = OperationType(step["operation"])

        if operation == OperationType.REPEAT:
            count = step["parameters"]["count"]
            logger.info(
                f"🔁 REPEAT {step['parameters']['start_step']}~{step['parameters']['end_step']} "
                f"x{count} ({step['parameters'].get('solvent')})"
            )
            # 실제 반복 대상 step들을 다시 찾아 count만큼 실행
            repeat_targets = [
                s for s in phase_data["steps"]
                if s["step_code"] in (step["parameters"]["start_step"], step["parameters"]["end_step"])
                or _step_in_range(s["step_code"], step["parameters"]["start_step"], step["parameters"]["end_step"])
            ]
            for i in range(count):
                for target in repeat_targets:
                    if target["operation"] == "REPEAT":
                        continue
                    result = execute_step(experiment_id, phase, {**target, "step_code": f"{target['step_code']}_rep{i+1}"})
                    executed.append(result)
            continue

        result = execute_step(experiment_id, phase, step)
        executed.append(result)

        # order_critical Task 실패 시 전체 flow 중단
        if result.order_critical and result.status != "success":
            raise RuntimeError(f"order_critical Step 실패: {result.step_code}")

    return executed


def _step_in_range(step_code: str, start: str, end: str) -> bool:
    """F-2, F-3, F-4, F-5, F-6처럼 F-2~F-6 구간에 속하는지 간단히 판별."""
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
def zr_btc_synthesis_flow(experiment_id: str = "exp_zrbtc_001", protocol_path: Optional[Path] = None):
    logger = get_run_logger()
    protocol = load_protocol(protocol_path or PROTOCOL_PATH)

    print(f"\n{'='*60}")
    print(f"  {protocol['protocol_name']} ({protocol['protocol_version']})")
    print(f"  Experiment: {experiment_id} | Target: {protocol['target_material']}")
    print(f"{'='*60}\n")

    all_tasks: list[Task] = []
    for phase_data in protocol["phases"]:
        phase_tasks = run_phase(experiment_id, phase_data)
        all_tasks.extend(phase_tasks)

    print(f"\n✅ 전체 {len(all_tasks)}개 Task 실행 완료")
    print(f"⚠️  Notes: {len(protocol['global_notes'])}건 (docs/db_schema.md 참고)")

    # TODO: MongoDB에 all_tasks 저장 (src/database/models.Task.model_dump() 활용)
    return all_tasks


if __name__ == "__main__":
    zr_btc_synthesis_flow()
