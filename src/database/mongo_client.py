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


if __name__ == "__main__":
    # 연결 테스트: python -m src.database.mongo_client
    database = get_database()
    init_collections(database)
    print(f"현재 컬렉션 목록: {database.list_collection_names()}")
