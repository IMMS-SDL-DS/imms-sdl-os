"""
PrecursorCatalog(물질 카탈로그) + Experiment Run 메타데이터 테스트.
(docs/precursor_catalog_and_run_metadata.md 설계 기준)
"""

import mongomock
import pytest

from src.database.models import (
    Experiment,
    MaterialRole,
    MaterialUsage,
    PrecursorCatalog,
)
from src.database.mongo_client import (
    find_precursor_by_name,
    get_precursor,
    register_precursor,
)


@pytest.fixture
def fake_db():
    return mongomock.MongoClient().db


# ── Experiment Run 메타데이터 ────────────────────────────────────────
def test_experiment_defaults_to_manual_execution_mode():
    """실험팀 Run 기록이 전부 manual이므로, 기본값도 manual이어야 함."""
    exp = Experiment(
        experiment_id="e1", name="Zn-BDC 4 pot synthesis",
        protocol_version="v1", target_material="Zn-BDC",
    )
    assert exp.execution_mode == "manual"


def test_experiment_stores_run_metadata():
    exp = Experiment(
        experiment_id="e1", name="ZBDC-BYJ-0000",
        protocol_version="v1", target_material="Zn-BDC",
        execution_mode="manual", sample_count=4,
        project_description="Zn-BDC 4 pot synthesis, Hydrostability test",
    )
    assert exp.sample_count == 4
    assert "Hydrostability" in exp.project_description


def test_experiment_supports_auto_mode_for_future_automation():
    exp = Experiment(
        experiment_id="e2", name="auto run",
        protocol_version="v1", target_material="Zr-BTC",
        execution_mode="auto",
    )
    assert exp.execution_mode == "auto"


# ── PrecursorCatalog ─────────────────────────────────────────────────
def test_precursor_catalog_stores_master_info():
    cat = PrecursorCatalog(
        precursor_id="MSP0001", name="Zinc oxide", cas_number="1314-13-2",
        formula="ZnO", vendor="Alfa aesar", storage_location="D4-3",
        package_scale=100, package_unit="g",
    )
    assert cat.formula == "ZnO"
    assert cat.storage_location == "D4-3"


def test_material_usage_references_precursor_id():
    """MaterialUsage가 이름이 아니라 precursor_id로 카탈로그를 명시적으로 참조하는지."""
    usage = MaterialUsage(
        material_name="Zinc oxide", role=MaterialRole.METAL,
        precursor_id="MSP0001", target_mass_mg=97,
    )
    assert usage.precursor_id == "MSP0001"


def test_material_usage_precursor_id_is_optional():
    """precursor_id 없이도 MaterialUsage가 만들어져야 함 (기존 데이터 호환성)."""
    usage = MaterialUsage(material_name="ZrOCl2", role=MaterialRole.METAL, target_mass_mg=97)
    assert usage.precursor_id is None


# ── mongo_client 저장/조회 ────────────────────────────────────────────
def test_register_and_get_precursor(fake_db):
    register_precursor(fake_db, PrecursorCatalog(
        precursor_id="MSP0002", name="Zinc cyanide, 98%", cas_number="557-21-1",
        formula="Zn(CN)2", vendor="ACROS",
    ))

    result = get_precursor(fake_db, "MSP0002")

    assert result["name"] == "Zinc cyanide, 98%"
    assert result["formula"] == "Zn(CN)2"


def test_register_precursor_upserts_by_id(fake_db):
    """같은 precursor_id로 다시 등록하면 갱신되어야 함 (중복 문서 방지)."""
    register_precursor(fake_db, PrecursorCatalog(precursor_id="MSP0003", name="Zinc oxide"))
    register_precursor(fake_db, PrecursorCatalog(precursor_id="MSP0003", name="Zinc oxide (수정됨)"))

    assert fake_db["precursor_catalog"].count_documents({"precursor_id": "MSP0003"}) == 1
    assert get_precursor(fake_db, "MSP0003")["name"] == "Zinc oxide (수정됨)"


def test_find_precursor_by_name(fake_db):
    register_precursor(fake_db, PrecursorCatalog(precursor_id="MSP0004", name="Zinc chloride"))

    result = find_precursor_by_name(fake_db, "Zinc chloride")

    assert result["precursor_id"] == "MSP0004"


def test_get_precursor_returns_none_when_not_found(fake_db):
    assert get_precursor(fake_db, "존재하지_않는_ID") is None
