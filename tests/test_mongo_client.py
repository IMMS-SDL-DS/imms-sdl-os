"""
src/database/mongo_client.py 테스트
실제 Atlas 연결 없이도 확인 가능한 부분만 테스트한다.
(실 연결 테스트는 .env 설정 후 `python -m src.database.mongo_client`로 수동 확인)
"""

import pytest

from src.database.mongo_client import COLLECTIONS, get_database


def test_collections_match_schema():
    """COLLECTIONS 목록이 docs/db_schema.md의 4개 컬렉션과 일치하는지."""
    assert set(COLLECTIONS) == {"experiment", "task", "device", "sample"}


def test_get_database_raises_without_env(monkeypatch):
    """.env가 없거나 MONGODB_URI가 비어있으면 명확한 에러를 던지는지."""
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.setattr("src.database.mongo_client.load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        get_database()
