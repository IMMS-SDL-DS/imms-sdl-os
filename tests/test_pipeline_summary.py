"""
DeviceState 저장/조회 + 파이프라인 최종 로그 통합(get_pipeline_summary) 테스트.
"""

import mongomock
import pytest

from src.database.models import (
    MaterialRole,
    MaterialUsage,
    OperationType,
    Task,
)
from src.database.mongo_client import (
    get_device_state,
    get_pipeline_summary,
    save_device_state,
)
from src.database.models import DeviceState


@pytest.fixture
def fake_db():
    return mongomock.MongoClient().db


def test_save_and_get_device_state(fake_db):
    save_device_state(fake_db, DeviceState(
        device_id="dev_multidose", door_status="closed",
        current_reading_mg=95.2, is_stable=True,
    ))

    state = get_device_state(fake_db, "dev_multidose")
    assert state["door_status"] == "closed"
    assert state["is_stable"] is True


def test_save_device_state_overwrites_previous_snapshot(fake_db):
    """DeviceState는 이력이 아니라 최신 스냅샷만 유지해야 함."""
    save_device_state(fake_db, DeviceState(device_id="dev_x", door_status="open"))
    save_device_state(fake_db, DeviceState(device_id="dev_x", door_status="closed"))

    assert fake_db["device_state"].count_documents({"device_id": "dev_x"}) == 1
    assert get_device_state(fake_db, "dev_x")["door_status"] == "closed"


def test_get_pipeline_summary_includes_material_usage_and_errors(fake_db):
    task = Task(
        task_id="e1_t1", experiment_id="e1", phase="B", step_code="B-1",
        operation=OperationType.DISPENSE_SOLID,
        parameters={"reagent": "ZrOCl2", "mass_mg": 97, "vessel": "V1"},
        status="success",
        material_usage=MaterialUsage(
            material_name="ZrOCl2", role=MaterialRole.METAL,
            target_mass_mg=97, actual_mass_mg=95.2,
        ),
    )
    fake_db["task"].insert_one(task.model_dump())

    summary = get_pipeline_summary(fake_db, "e1")

    assert len(summary) == 1
    assert summary[0]["task_id"] == "e1_t1"
    assert summary[0]["material_usage"]["actual_mass_mg"] == 95.2


def test_get_pipeline_summary_only_returns_matching_experiment(fake_db):
    for exp_id, task_id in [("e1", "t1"), ("e2", "t2")]:
        t = Task(
            task_id=task_id, experiment_id=exp_id, phase="B", step_code="B-1",
            operation=OperationType.DISPENSE_SOLID,
            parameters={"reagent": "X", "mass_mg": 10, "vessel": "V"},
        )
        fake_db["task"].insert_one(t.model_dump())

    summary = get_pipeline_summary(fake_db, "e1")
    assert [s["task_id"] for s in summary] == ["t1"]
