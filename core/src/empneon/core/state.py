"""Persist the latest generic agent-state snapshot."""

import dataclasses
import sqlite3
from collections.abc import Mapping

from empneon.core.contracts import AgentStateSnapshot
from empneon.core.memory.documents import DocumentMemoryStore

NAMESPACE = "core.agent-state.v1"


def save_agent_state(
    conn: sqlite3.Connection, snapshot: AgentStateSnapshot
) -> AgentStateSnapshot:
    DocumentMemoryStore(conn).set(NAMESPACE, snapshot.agent_id, dataclasses.asdict(snapshot))
    return snapshot


def load_agent_state(
    conn: sqlite3.Connection, agent_id: str
) -> AgentStateSnapshot | None:
    value = DocumentMemoryStore(conn).get(NAMESPACE, str(agent_id))
    return AgentStateSnapshot.from_mapping(value) if isinstance(value, Mapping) else None
