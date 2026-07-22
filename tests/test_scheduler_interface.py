"""
Mehdi의 Learning-Aware Scheduler와의 인터페이스 테스트.
job schema {value, duration, device, precedence, deadline}를
DB에서 읽고, 스케줄러가 계산한 순서를 다시 쓰는 왕복(round-trip)을 검증한다.
"""

from datetime import datetime, timedelta

import mongomock
import pytest

from src.database.models import OperationType, Task
from src.database.mongo_client import apply_scheduler_ordering, get_scheduler_job_queue


@pytest.fixture
def fake_db():
    return mongomock.MongoClient().db


def _make_task(task_id, experiment_id="e1", status="pending", **scheduler_kwargs):
    return Task(
        task_id=task_id,
        experiment_id=experiment_id,
        phase="B",
        step_code=f"STEP_{task_id}",
        operation=OperationType.DISPENSE_SOLID,
        parameters={"reagent": "ZrOCl2", "mass_mg": 97, "vessel": "V1"},
        device_id="dev_multidose",
        status=status,
        **scheduler_kwargs,
    )


def test_to_scheduler_job_matches_contract():
    """Task.to_scheduler_job()이 정확히 {value, duration, device, precedence, deadline} 형태인지."""
    deadline = datetime.now() + timedelta(days=3)
    task = _make_task(
        "j1",
        scheduler_value=0.9,
        scheduler_duration_estimate_sec=120,
        scheduler_precedence=["j0"],
        scheduler_deadline=deadline,
    )
    job = task.to_scheduler_job()

    assert job["job_id"] == "j1"
    assert job["value"] == 0.9
    assert job["duration"] == 120
    assert job["device"] == "dev_multidose"
    assert job["precedence"] == ["j0"]
    assert job["deadline"] == deadline


def test_get_scheduler_job_queue_only_returns_pending(fake_db):
    """status가 pending인 Task만 큐에 포함되어야 함 (이미 실행된 건 스케줄링 대상이 아님)."""
    fake_db["task"].insert_one(_make_task("j1", status="pending").model_dump())
    fake_db["task"].insert_one(_make_task("j2", status="success").model_dump())
    fake_db["task"].insert_one(_make_task("j3", status="running").model_dump())

    queue = get_scheduler_job_queue(fake_db)

    job_ids = [j["job_id"] for j in queue]
    assert job_ids == ["j1"]


def test_get_scheduler_job_queue_filters_by_experiment(fake_db):
    """experiment_id를 주면 그 캠페인의 job만 반환해야 함."""
    fake_db["task"].insert_one(_make_task("j1", experiment_id="campaign_A").model_dump())
    fake_db["task"].insert_one(_make_task("j2", experiment_id="campaign_B").model_dump())

    queue = get_scheduler_job_queue(fake_db, experiment_id="campaign_A")

    assert len(queue) == 1
    assert queue[0]["job_id"] == "j1"


def test_apply_scheduler_ordering_writes_priority(fake_db):
    """스케줄러가 계산한 순서(ordering)가 낮은 숫자=먼저 실행으로 저장되는지."""
    fake_db["task"].insert_one(_make_task("j1").model_dump())
    fake_db["task"].insert_one(_make_task("j2").model_dump())
    fake_db["task"].insert_one(_make_task("j3").model_dump())

    updated = apply_scheduler_ordering(fake_db, ["j3", "j1", "j2"])

    assert updated == 3
    assert fake_db["task"].find_one({"task_id": "j3"})["scheduler_priority"] == 0
    assert fake_db["task"].find_one({"task_id": "j1"})["scheduler_priority"] == 1
    assert fake_db["task"].find_one({"task_id": "j2"})["scheduler_priority"] == 2


def test_precedence_is_separate_from_material_refs():
    """scheduler_precedence(순서 제약)와 input_refs(물질 흐름)는 서로 다른 개념이어야 함."""
    task = _make_task(
        "j1",
        scheduler_precedence=["j0"],
    )
    task.input_refs = ["sample_x"]

    assert task.scheduler_precedence == ["j0"]
    assert task.input_refs == ["sample_x"]
    assert task.scheduler_precedence != task.input_refs
