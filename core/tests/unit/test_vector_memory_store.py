import sqlite3
from pathlib import Path

import pytest

from empneon.core.memory.vector import VectorMemoryStore
from empneon.db.connection import open_db

DIM = 4


@pytest.fixture
def store() -> VectorMemoryStore:
    conn = open_db(":memory:")
    return VectorMemoryStore(conn, dimensions=DIM)


def _vec(x: float, y: float = 0.0, z: float = 0.0, w: float = 0.0) -> list[float]:
    return [x, y, z, w]


def test_upsert_and_search_returns_nearest(store: VectorMemoryStore) -> None:
    store.upsert("evt-a", _vec(1.0))
    store.upsert("evt-b", _vec(0.0, 1.0))
    store.upsert("evt-c", _vec(0.0, 0.0, 1.0))
    results = store.search(_vec(1.0), limit=3)
    assert results[0][0] == "evt-a"
    assert results[0][1] == pytest.approx(0.0, abs=1e-5)


def test_search_returns_limit(store: VectorMemoryStore) -> None:
    for i in range(5):
        store.upsert(f"evt-{i}", _vec(float(i)))
    results = store.search(_vec(0.0), limit=2)
    assert len(results) == 2


def test_search_empty_store_returns_empty(store: VectorMemoryStore) -> None:
    assert store.search(_vec(1.0)) == []


def test_upsert_replaces_existing(store: VectorMemoryStore) -> None:
    store.upsert("evt-x", _vec(1.0))
    store.upsert("evt-x", _vec(0.0, 1.0))  # replace with orthogonal vector
    results = store.search(_vec(0.0, 1.0), limit=1)
    assert results[0][0] == "evt-x"
    assert results[0][1] == pytest.approx(0.0, abs=1e-5)


def test_delete_removes_from_search(store: VectorMemoryStore) -> None:
    store.upsert("evt-gone", _vec(1.0))
    store.delete("evt-gone")
    results = store.search(_vec(1.0))
    assert all(r[0] != "evt-gone" for r in results)


def test_delete_nonexistent_is_noop(store: VectorMemoryStore) -> None:
    store.delete("does-not-exist")  # must not raise


def test_search_result_ordered_by_distance(store: VectorMemoryStore) -> None:
    store.upsert("near", _vec(1.0, 0.1))
    store.upsert("far", _vec(0.0, 1.0))
    results = store.search(_vec(1.0), limit=2)
    assert results[0][0] == "near"
    assert results[0][1] < results[1][1]


def test_rejects_wrong_embedding_dimensions(store: VectorMemoryStore) -> None:
    with pytest.raises(ValueError, match="expected 4 dimensions, got 2"):
        store.upsert("bad", [1.0, 2.0])


def test_distance_is_euclidean_not_cosine(store: VectorMemoryStore) -> None:
    store.upsert("evt-unit", _vec(1.0))
    (event_id, distance), = store.search(_vec(3.0), limit=1)
    assert event_id == "evt-unit"
    # Cosine distance would be 0.0 (same direction); L2 distance is 2.0.
    assert distance == pytest.approx(2.0, abs=1e-5)


def test_search_works_without_row_factory() -> None:
    conn = sqlite3.connect(":memory:")
    store = VectorMemoryStore(conn, dimensions=DIM)
    store.upsert("evt-a", _vec(1.0))
    assert store.search(_vec(1.0), limit=1)[0][0] == "evt-a"


def test_reopen_with_different_dimensions_is_rejected(tmp_path: Path) -> None:
    conn = open_db(str(tmp_path / "vec.sqlite3"))
    VectorMemoryStore(conn, dimensions=DIM)
    with pytest.raises(ValueError, match="dimensions"):
        VectorMemoryStore(conn, dimensions=DIM + 1)


def test_reopen_with_same_dimensions_is_allowed(tmp_path: Path) -> None:
    conn = open_db(str(tmp_path / "vec.sqlite3"))
    VectorMemoryStore(conn, dimensions=DIM).upsert("evt-a", _vec(1.0))
    assert VectorMemoryStore(conn, dimensions=DIM).search(_vec(1.0), limit=1)[0][0] == "evt-a"
