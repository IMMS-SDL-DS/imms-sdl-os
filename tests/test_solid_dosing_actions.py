"""
고체 분주 Action 레벨 모델 테스트 (docs/solid_dosing_workflow.md 설계 기준).
"""

import pytest

from src.database.models import (
    Action,
    ActionType,
    MaterialRole,
    MaterialUsage,
    OperationType,
    SOLID_DOSING_ACTION_SEQUENCE,
    Task,
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


def test_build_solid_dosing_actions_creates_13_steps():
    """12단계 workflow가 RETRACT+DOOR_CLOSE 분리로 13개 Action이 되어야 함."""
    task = _make_dispense_task()
    actions = task.build_solid_dosing_actions()

    assert len(actions) == 13
    assert len(task.actions) == 13
    assert all(isinstance(a, Action) for a in actions)


def test_action_sequence_order_matches_workflow():
    """설계 문서의 12단계 순서와 ActionType 매핑이 정확히 일치하는지."""
    task = _make_dispense_task()
    actions = task.build_solid_dosing_actions()

    expected_types = [
        ActionType.PICK, ActionType.MOUNT, ActionType.PICK, ActionType.DOOR_OPEN,
        ActionType.PLACE, ActionType.RETRACT, ActionType.DOOR_CLOSE, ActionType.DOSE,
        ActionType.DOOR_OPEN, ActionType.PICK, ActionType.DOOR_CLOSE, ActionType.PLACE,
        ActionType.PLACE,
    ]
    assert [a.action_type for a in actions] == expected_types
    assert [a.sequence_index for a in actions] == list(range(1, 14))


def test_only_door_close_after_retract_is_safety_critical():
    """RETRACT 직후 DOOR_CLOSE(7번)만 safety_critical=True, 나머지는 False."""
    task = _make_dispense_task()
    actions = task.build_solid_dosing_actions()

    safety_critical_indices = [a.sequence_index for a in actions if a.safety_critical]
    assert safety_critical_indices == [7]


def test_validate_action_safety_order_passes_when_retract_succeeded():
    """RETRACT가 success면 DOOR_CLOSE 진행 검증을 통과해야 함."""
    task = _make_dispense_task()
    task.build_solid_dosing_actions()
    task.actions[5].status = "success"  # RETRACT (sequence 6)
    task.actions[6].status = "running"  # DOOR_CLOSE (sequence 7)

    task.validate_action_safety_order()  # 예외 없이 통과해야 함


def test_validate_action_safety_order_raises_when_retract_failed():
    """RETRACT가 failed인데 DOOR_CLOSE를 진행하면 반드시 에러가 나야 함
    (로봇팔-문 물리적 충돌 방지)."""
    task = _make_dispense_task()
    task.build_solid_dosing_actions()
    task.actions[5].status = "failed"  # RETRACT 실패
    task.actions[6].status = "running"

    with pytest.raises(ValueError, match="안전 순서 위반"):
        task.validate_action_safety_order()


def test_material_usage_attaches_to_task():
    """MaterialUsage가 Task에 정상적으로 붙고 필드가 보존되는지."""
    task = _make_dispense_task()
    task.material_usage = MaterialUsage(
        material_name="ZrOCl2",
        role=MaterialRole.METAL,
        concentration=0.5,
        concentration_unit="M",
        target_mass_mg=97,
        head_id="head_ZrOCl2",
        vial_id="vial_003",
    )

    assert task.material_usage.role == MaterialRole.METAL
    assert task.material_usage.target_mass_mg == 97
    assert task.material_usage.actual_mass_mg is None  # 아직 VERIFY_MASS 전


def test_material_usage_records_actual_mass_after_verification():
    """VERIFY_MASS 이후 actual_mass_mg가 채워지는 시나리오."""
    usage = MaterialUsage(
        material_name="BTC", role=MaterialRole.LIGAND, target_mass_mg=21
    )
    usage.actual_mass_mg = 20.8  # 실측 후 갱신

    assert usage.actual_mass_mg == 20.8
    assert usage.target_mass_mg == 21


def test_action_sequence_template_length():
    """템플릿 자체가 13개 항목을 갖고 있는지 (설계 문서와 동기화 확인용)."""
    assert len(SOLID_DOSING_ACTION_SEQUENCE) == 13
