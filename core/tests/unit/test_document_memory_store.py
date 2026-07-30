import time

from empneon.core.memory.documents import DocumentMemoryStore
from empneon.db.connection import open_db


def test_document_memory_is_namespaced_and_json_serializable() -> None:
    store = DocumentMemoryStore(open_db(":memory:"))

    store.set("adapter.profile", "bella", {"name": "Bella", "traits": ["family"]})
    store.set("adapter.profile", "mortimer", {"name": "Mortimer"})
    store.set("adapter.summary", "bella:mortimer", {"summary": "Friends"})

    assert store.get("adapter.profile", "bella") == {
        "name": "Bella",
        "traits": ["family"],
    }
    assert [item.key for item in store.list("adapter.profile")] == ["mortimer", "bella"]
    assert store.get("adapter.profile", "missing") is None


def test_document_timestamp_uses_unix_seconds() -> None:
    before = int(time.time())
    document = DocumentMemoryStore(open_db(":memory:")).set("adapter.profile", "bella", {})

    assert before <= document.updated_at <= int(time.time())
