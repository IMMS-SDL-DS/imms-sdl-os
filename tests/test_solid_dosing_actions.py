"""
고체 분주 Action 레벨 모델 + 데이터 파이프라인/예외처리 모델 테스트.
(docs/solid_dosing_workflow.md, docs/data_pipeline_and_error_handling.md 설계 기준)
"""

import pytest

from src.database.models import (
    Action,
    ActionType,
    DeviceState,
    ErrorCategory,
    ErrorRecord,
    MaterialRole,
    MaterialUsage,
    OperationType,
    SOLID_DOSING_ACTION_SEQUENCE,
    Task,
    TaskHandoff,
    ToleranceDecision,
    decide_tolerance,
)


def _make_dispense_task(task_id="exp1_dispense1"):
    return Task(
        task_id=task_id,
        experiment_id="exp1",
        phase="B",
        step_code="B-1",
        operation=OperationType.DISPENSE_SOLID,
        parameters={"reagent": "ZrOCl2", "mass_mg": 97, "vessel": "V1"},
        device_id="dev_multidose",
    )


# ── Action 시퀀스 (15단계: STABILIZE 2회 추가) ─────────────────────────
def test_build_solid_dosing_actions_creates_16_steps():
    """12단계 workflow가 RETRACT×2 + DOOR_CLOSE 분리 + STABILIZE 2회 추가로 16개가 되어야 함."""
    task = _make_dispense_task()
    actions = task.build_solid_dosing_actions()

    assert len(actions) == 16
    assert len(task.actions) == 16
    assert all(isinstance(a, Action) for a in actions)


def test_action_sequence_order_matches_workflow():
    """설계 문서의 순서와 ActionType 매핑이 정확히 일치하는지 (STABILIZE 삽입 위치 포함)."""
    task = _make_dispense_task()
    actions = task.build_solid_dosing_actions()

    expected_types = [
        ActionType.PICK, ActionType.MOUNT, ActionType.PICK, ActionType.DOOR_OPEN,
        ActionType.PLACE, ActionType.RETRACT, ActionType.DOOR_CLOSE,
        ActionType.STABILIZE, ActionType.DOSE, ActionType.STABILIZE,
        ActionType.DOOR_OPEN, ActionType.PICK, ActionType.RETRACT, ActionType.DOOR_CLOSE,
        ActionType.PLACE, ActionType.PLACE,
    ]
    assert [a.action_type for a in actions] == expected_types
    assert [a.sequence_index for a in actions] == list(range(1, 17))


def test_stabilize_actions_have_wait_parameters():
    """STABILIZE Action들이 stability_threshold_mg/max_wait_sec 파라미터를 갖고 있는지."""
    task = _make_dispense_task()
    actions = task.build_solid_dosing_actions()

    stabilize_actions = [a for a in actions if a.action_type == ActionType.STABILIZE]
    assert len(stabilize_actions) == 2
    for a in stabilize_actions:
        assert "stability_threshold_mg" in a.parameters
        assert "max_wait_sec" in a.parameters


def test_door_close_after_retract_is_safety_critical():
    """두 DOOR_CLOSE(7번, 14번) 모두 직전 RETRACT 확인이 필요 — 대칭 설계 (로봇-문 충돌 방지)."""
    task = _make_dispense_task()
    actions = task.build_solid_dosing_actions()

    safety_critical_indices = [a.sequence_index for a in actions if a.safety_critical]
    assert safety_critical_indices == [7, 14]


def test_validate_action_safety_order_passes_when_retract_succeeded():
    """두 RETRACT→DOOR_CLOSE 쌍(7,14번) 모두 정상이면 예외가 없어야 함."""
    task = _make_dispense_task()
    task.build_solid_dosing_actions()
    task.actions[5].status = "success"   # RETRACT #6
    task.actions[6].status = "running"   # DOOR_CLOSE #7
    task.actions[12].status = "success"  # RETRACT #13
    task.actions[13].status = "running"  # DOOR_CLOSE #14

    task.validate_action_safety_order()  # 예외 없이 통과해야 함


def test_validate_action_safety_order_raises_when_retract_failed():
    task = _make_dispense_task()
    task.build_solid_dosing_actions()
    task.actions[5].status = "failed"
    task.actions[6].status = "running"

    with pytest.raises(ValueError, match="안전 순서 위반"):
        task.validate_action_safety_order()


def test_validate_action_safety_order_raises_on_second_retract_door_close_pair():
    """두 번째 RETRACT(13번)가 실패해도 대칭적으로 안전 위반이 잡혀야 함."""
    task = _make_dispense_task()
    task.build_solid_dosing_actions()
    task.actions[5].status = "success"
    task.actions[6].status = "success"
    task.actions[12].status = "failed"   # RETRACT #13 실패
    task.actions[13].status = "running"  # DOOR_CLOSE #14

    with pytest.raises(ValueError, match="안전 순서 위반"):
        task.validate_action_safety_order()


def test_action_sequence_template_length():
    assert len(SOLID_DOSING_ACTION_SEQUENCE) == 16


# ── Material 추적 + 오차율 ────────────────────────────────────────────
def test_material_usage_attaches_to_task():
    task = _make_dispense_task()
    task.material_usage = MaterialUsage(
        material_name="ZrOCl2", role=MaterialRole.METAL,
        concentration=0.5, concentration_unit="M",
        target_mass_mg=97, head_id="head_ZrOCl2", vial_id="vial_003",
    )

    assert task.material_usage.role == MaterialRole.METAL
    assert task.material_usage.actual_mass_mg is None


def test_compute_error_rate_after_actual_mass_recorded():
    usage = MaterialUsage(material_name="ZrOCl2", role=MaterialRole.METAL, target_mass_mg=100)
    assert usage.compute_error_rate() is None  # actual 아직 없음

    usage.actual_mass_mg = 95.0
    rate = usage.compute_error_rate()

    assert rate == pytest.approx(-5.0)
    assert usage.error_rate_pct == pytest.approx(-5.0)


# ── 오차 범위 판단 (ToleranceDecision) ────────────────────────────────
def test_decide_tolerance_within_tolerance():
    result = decide_tolerance(target_mass_mg=97, actual_mass_mg=95.2, tolerance_mg=5)
    assert result == ToleranceDecision.WITHIN_TOLERANCE


def test_decide_tolerance_triggers_correction_when_under_target():
    result = decide_tolerance(
        target_mass_mg=97, actual_mass_mg=80, tolerance_mg=5, correction_attempts=0
    )
    assert result == ToleranceDecision.CORRECTION_DOSE


def test_decide_tolerance_fails_after_max_correction_attempts():
    result = decide_tolerance(
        target_mass_mg=97, actual_mass_mg=80, tolerance_mg=5,
        correction_attempts=2, max_correction_attempts=2,
    )
    assert result == ToleranceDecision.FAIL_VIAL


def test_decide_tolerance_over_target_does_not_trigger_correction():
    """목표보다 많이 들어간 경우는 보정(추가 도징)으로 해결이 안 되므로 바로 FAIL_VIAL."""
    result = decide_tolerance(
        target_mass_mg=97, actual_mass_mg=110, tolerance_mg=5, correction_attempts=0
    )
    assert result == ToleranceDecision.FAIL_VIAL


# ── 에러 로깅 ─────────────────────────────────────────────────────────
def test_error_record_attaches_to_task():
    task = _make_dispense_task()
    task.errors.append(ErrorRecord(
        error_id="err1", task_id=task.task_id,
        category=ErrorCategory.STABILIZATION_TIMEOUT,
        message="저울 값이 30초 안에 안정화되지 않음",
    ))

    assert len(task.errors) == 1
    assert task.errors[0].category == ErrorCategory.STABILIZATION_TIMEOUT


# ── DeviceState ───────────────────────────────────────────────────────
def test_device_state_records_physical_status():
    state = DeviceState(
        device_id="dev_multidose", door_status="closed",
        current_reading_mg=95.2, is_stable=True, safety_sensor_active=True,
    )

    assert state.door_status == "closed"
    assert state.is_stable is True


# ── TaskHandoff ───────────────────────────────────────────────────────
def test_task_handoff_carries_actual_material_usage_to_next_task():
    """고체 분주 Task의 actual_mass_mg가 TaskHandoff를 통해 다음 Task로 전달되는지."""
    task = _make_dispense_task()
    task.material_usage = MaterialUsage(
        material_name="ZrOCl2", role=MaterialRole.METAL,
        target_mass_mg=97, actual_mass_mg=95.2,
    )
    task.output_refs = ["sample_metal_sol"]
    task.status = "success"

    handoff = TaskHandoff.from_task(task)

    assert handoff.status == "success"
    assert handoff.material_usage.actual_mass_mg == 95.2
    assert handoff.output_sample_ids == ["sample_metal_sol"]


def test_task_handoff_from_task_carries_errors():
    task = _make_dispense_task()
    task.status = "failed"
    task.errors.append(ErrorRecord(
        error_id="err1", task_id=task.task_id,
        category=ErrorCategory.TARGET_NOT_REACHED,
        message="보정 한도 초과",
    ))

    handoff = TaskHandoff.from_task(task)

    assert handoff.status == "failed"
    assert len(handoff.errors) == 1
