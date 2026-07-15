"""
Device 상태 관리(락) 테스트.
실제 MongoDB Atlas 연결 없이, mongomock으로 로컬에서 동일한 동작을 검증한다.
"""

import mongomock
import pytest

from src.database.mongo_client import (
    register_device_if_missing,
    release_device,
    try_acquire_device,
)
from src.pipeline.dispense_command import run_dispense_command


@pytest.fixture
def fake_db():
    return mongomock.MongoClient().db


def test_register_device_creates_idle_by_default(fake_db):
    register_device_if_missing(fake_db, "dev_x", "X", "solid_dispenser")
    doc = fake_db["device"].find_one({"device_id": "dev_x"})
    assert doc["status"] == "idle"


def test_register_device_does_not_overwrite_busy_status(fake_db):
    """이미 busy인 장비에 register를 다시 호출해도 상태가 안 바뀌어야 함."""
    register_device_if_missing(fake_db, "dev_x", "X", "solid_dispenser")
    fake_db["device"].update_one({"device_id": "dev_x"}, {"$set": {"status": "busy"}})

    register_device_if_missing(fake_db, "dev_x", "X", "solid_dispenser")
    doc = fake_db["device"].find_one({"device_id": "dev_x"})
    assert doc["status"] == "busy"


def test_second_acquire_fails_while_first_holds_device(fake_db):
    """장비가 busy인 동안, 두 번째 acquire 시도는 반드시 실패해야 함 (충돌 방지)."""
    register_device_if_missing(fake_db, "dev_x", "X", "solid_dispenser")

    first = try_acquire_device(fake_db, "dev_x")
    second = try_acquire_device(fake_db, "dev_x")

    assert first is True
    assert second is False


def test_release_allows_next_acquire(fake_db):
    register_device_if_missing(fake_db, "dev_x", "X", "solid_dispenser")
    try_acquire_device(fake_db, "dev_x")

    release_device(fake_db, "dev_x")
    reacquired = try_acquire_device(fake_db, "dev_x")

    assert reacquired is True


def test_dispense_command_held_when_device_already_busy(monkeypatch, fake_db):
    """MultiDose가 이미 사용 중이면, run_dispense_command는 로봇을 호출하지 않고
    status='held'로 즉시 반환해야 한다."""
    monkeypatch.setattr(
        "src.pipeline.dispense_command.get_database", lambda: fake_db
    )

    # 다른 Task가 이미 MultiDose를 쓰는 중인 상황을 미리 만들어둠
    register_device_if_missing(fake_db, "dev_multidose", "MultiDose", "solid_dispenser")
    try_acquire_device(fake_db, "dev_multidose")

    driver_called = {"count": 0}

    def fake_driver(reagent, target_mass_mg, tolerance_mg, vessel):
        driver_called["count"] += 1
        return {"actual_mass_mg": target_mass_mg, "success": True}

    task = run_dispense_command(
        "ZrOCl2", 97, "Vial_10mL", robot_driver=fake_driver, save_to_db=True
    )

    assert task.status == "held"
    assert driver_called["count"] == 0  # 로봇이 실제로 호출되지 않아야 함


def test_dispense_command_releases_device_after_success(monkeypatch, fake_db):
    """정상 실행 후에는 장비가 다시 idle로 돌아와야 한다 (다음 Task가 쓸 수 있게)."""
    monkeypatch.setattr(
        "src.pipeline.dispense_command.get_database", lambda: fake_db
    )

    def fake_driver(reagent, target_mass_mg, tolerance_mg, vessel):
        return {"actual_mass_mg": target_mass_mg, "success": True}

    task = run_dispense_command(
        "ZrOCl2", 97, "Vial_10mL", robot_driver=fake_driver, save_to_db=True
    )

    assert task.status == "success"
    doc = fake_db["device"].find_one({"device_id": "dev_multidose"})
    assert doc["status"] == "idle"
