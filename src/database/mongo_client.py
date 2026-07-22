"""
MOF SDL OS — MongoDB 연결 클라이언트
=====================================
.env 파일의 MONGODB_URI / MONGODB_DB_NAME을 읽어 MongoDB Atlas에 연결한다.
data/schema/mongo_schema_v2.json의 $jsonSchema validator를 컬렉션에 적용하고,
src.database.models의 Pydantic 모델(Experiment/Task/Device/Sample)을
그대로 저장/조회할 수 있는 헬퍼 함수를 제공한다.

사용 전 준비:
    pip install pymongo python-dotenv --break-system-packages
    .env 파일에 MONGODB_URI, MONGODB_DB_NAME 설정 (README 참고, git에는 올리지 않음)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import CollectionInvalid, ConnectionFailure

from src.database.models import Device, Experiment, Sample, Task

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "mongo_schema_v2.json"

# 4개 핵심 컬렉션 이름 (docs/db_schema.md와 동일하게 유지)
COLLECTIONS = ["experiment", "task", "device", "sample"]


def get_database() -> Database:
    """.env를 읽어 MongoDB Atlas에 연결하고 Database 객체를 반환한다."""
    load_dotenv(REPO_ROOT / ".env")

    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "imms_sdl_os")

    if not uri:
        raise RuntimeError(
            "MONGODB_URI가 설정되지 않았습니다. "
            "repo 최상단에 .env 파일을 만들고 MONGODB_URI=... 를 넣어주세요."
        )

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except ConnectionFailure as e:
        raise RuntimeError(
            "MongoDB 연결 실패. Atlas의 'Network Access'에서 현재 IP가 허용되어 있는지, "
            "비밀번호가 맞는지 확인하세요."
        ) from e

    print(f"✅ MongoDB 연결 성공: db='{db_name}'")
    return client[db_name]


def init_collections(db: Database, schema_path: Path = SCHEMA_PATH) -> None:
    """mongo_schema_v2.json의 $jsonSchema validator로 4개 컬렉션을 생성/갱신한다."""
    with open(schema_path, "r", encoding="utf-8") as f:
        schemas = json.load(f)

    for name in COLLECTIONS:
        validator = schemas[name]
        if name in db.list_collection_names():
            db.command("collMod", name, validator=validator, validationLevel="moderate")
            print(f"  ↻ 컬렉션 '{name}' validator 갱신")
        else:
            try:
                db.create_collection(name, validator=validator)
                print(f"  + 컬렉션 '{name}' 생성 (validator 적용)")
            except CollectionInvalid:
                print(f"  (이미 존재) '{name}'")

    # 자주 조회할 필드에 인덱스 생성 (Reference Edge 추적 성능용)
    db["task"].create_index("experiment_id")
    db["task"].create_index("step_code")
    db["sample"].create_index("experiment_id")
    db["sample"].create_index("produced_by_task_id")
    db["device"].create_index("device_id", unique=True)
    print("  ✓ 인덱스 생성 완료")


# ── 저장 헬퍼 (Pydantic 모델 → MongoDB 문서) ─────────────────────────
def save_experiment(db: Database, exp: Experiment) -> str:
    result = db["experiment"].update_one(
        {"experiment_id": exp.experiment_id},
        {"$set": exp.model_dump()},
        upsert=True,
    )
    return exp.experiment_id if result.upserted_id is None else str(result.upserted_id)


def save_task(db: Database, task: Task) -> str:
    result = db["task"].update_one(
        {"task_id": task.task_id},
        {"$set": task.model_dump()},
        upsert=True,
    )
    return task.task_id if result.upserted_id is None else str(result.upserted_id)


def save_device(db: Database, device: Device) -> str:
    result = db["device"].update_one(
        {"device_id": device.device_id},
        {"$set": device.model_dump()},
        upsert=True,
    )
    return device.device_id if result.upserted_id is None else str(result.upserted_id)


def save_sample(db: Database, sample: Sample) -> str:
    result = db["sample"].update_one(
        {"sample_id": sample.sample_id},
        {"$set": sample.model_dump()},
        upsert=True,
    )
    return sample.sample_id if result.upserted_id is None else str(result.upserted_id)


# ── 조회 헬퍼 ─────────────────────────────────────────────────────────
def get_tasks_by_experiment(db: Database, experiment_id: str) -> list[dict]:
    return list(db["task"].find({"experiment_id": experiment_id}).sort("step_code", 1))


def get_sample_lineage(db: Database, sample_id: str) -> Optional[dict]:
    """Sample 하나가 어떤 Task에서 생성되고 어디에 쓰였는지 역추적 (Provenance)."""
    sample = db["sample"].find_one({"sample_id": sample_id})
    if not sample:
        return None
    produced_by = None
    if sample.get("produced_by_task_id"):
        produced_by = db["task"].find_one({"task_id": sample["produced_by_task_id"]})
    consumed_by = list(
        db["task"].find({"task_id": {"$in": sample.get("consumed_by_task_ids", [])}})
    )
    return {"sample": sample, "produced_by": produced_by, "consumed_by": consumed_by}


# ── Device 상태 관리 (OCTOPUS 논문의 masking table 개념) ─────────────
# 여러 실험/Task가 같은 장비(예: Opentron Flex, MultiDose)를 공유할 때,
# 동시에 두 Task가 같은 장비를 쓰려고 하면 물리적 충돌이 생길 수 있다.
# MongoDB의 find_one_and_update는 "조건 확인 + 값 변경"을 하나의 원자적(atomic)
# 연산으로 처리해주기 때문에, 두 프로세스가 동시에 같은 장비를 요청해도
# 반드시 하나만 성공하도록 보장된다 (경쟁 상태race condition 방지).

def register_device_if_missing(
    db: Database,
    device_id: str,
    name: str,
    device_type: str,
    connection: str = "python_api",
    shared_phases: Optional[list[str]] = None,
) -> None:
    """
    장비가 device 컬렉션에 없으면 idle 상태로 새로 등록한다.
    이미 있으면 아무것도 안 바꾼다 ($setOnInsert) — 다른 Task가 이미
    busy로 표시해둔 장비의 상태를 실수로 되돌리지 않기 위함.
    """
    db["device"].update_one(
        {"device_id": device_id},
        {
            "$setOnInsert": {
                "device_id": device_id,
                "name": name,
                "device_type": device_type,
                "connection": connection,
                "shared_phases": shared_phases or [],
                "status": "idle",
                "last_used_at": None,
            }
        },
        upsert=True,
    )


def try_acquire_device(db: Database, device_id: str) -> bool:
    """
    장비를 "busy"로 표시하려고 시도한다.
    지금 상태가 정확히 "idle"일 때만 "busy"로 바뀌고 True를 반환한다.
    이미 busy(다른 Task가 쓰는 중)라면 아무것도 안 바뀌고 False를 반환한다.
    이 확인+변경이 하나의 원자적 연산이라, 두 Task가 동시에 호출해도
    반드시 하나만 True를 받는다.
    """
    result = db["device"].find_one_and_update(
        {"device_id": device_id, "status": "idle"},
        {"$set": {"status": "busy", "last_used_at": datetime.now()}},
    )
    return result is not None


def release_device(db: Database, device_id: str) -> None:
    """장비를 다시 idle 상태로 되돌린다 (Task 성공/실패와 무관하게 항상 호출해야 함)."""
    db["device"].update_one(
        {"device_id": device_id},
        {"$set": {"status": "idle", "last_used_at": datetime.now()}},
    )


# ── Scheduler 인터페이스 (Mehdi의 Learning-Aware Scheduler와의 read/write 계약) ──
# 스케줄러는 이 DB를 통해 job schema {value, duration, device, precedence, deadline}를
# 읽고, 계산한 실행 순서(ordering)를 다시 써넣는다.
# 자세한 계약 내용은 docs/scheduler_interface.md 참고.

def get_scheduler_job_queue(db: Database, experiment_id: Optional[str] = None) -> list[dict]:
    """
    스케줄링 대상 Task들을 job schema 형태로 반환한다.
    status="pending"인 Task만 대상 (아직 실행 안 됐고, 순서를 기다리는 것들).
    experiment_id를 주면 그 실험(캠페인)으로 범위를 좁힌다.
    """
    query = {"status": "pending"}
    if experiment_id:
        query["experiment_id"] = experiment_id

    jobs = []
    for doc in db["task"].find(query):
        jobs.append({
            "job_id": doc["task_id"],
            "value": doc.get("scheduler_value"),
            "duration": doc.get("scheduler_duration_estimate_sec"),
            "device": doc.get("device_id"),
            "precedence": doc.get("scheduler_precedence", []),
            "deadline": doc.get("scheduler_deadline"),
        })
    return jobs


def apply_scheduler_ordering(db: Database, ordering: list[str]) -> int:
    """
    스케줄러가 계산한 실행 순서를 DB에 반영한다.
    ordering은 task_id 리스트이며, 리스트 순서대로 0, 1, 2, ...가
    각 Task의 scheduler_priority로 저장된다 (낮을수록 먼저 실행).
    반영된 Task 개수를 반환한다.
    """
    updated = 0
    for priority, task_id in enumerate(ordering):
        result = db["task"].update_one(
            {"task_id": task_id},
            {"$set": {"scheduler_priority": priority}},
        )
        updated += result.modified_count
    return updated


if __name__ == "__main__":
    # 연결 테스트: python -m src.database.mongo_client
    database = get_database()
    init_collections(database)
    print(f"현재 컬렉션 목록: {database.list_collection_names()}")
