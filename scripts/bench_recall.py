#!/usr/bin/env python3
"""Measure memory recall latency at realistic store sizes (issue #34, FTS5 go/no-go).

Seeds a throwaway SQLite database with synthetic ``confirmed_interaction`` events spread over a
small society, then times the recall paths that exist today and an FTS5 prototype for comparison:

* ``sims.recall_event_rows``    the pair-history SQL scan (``json_extract`` + ``instr`` term match)
* ``sims.recalled_memories``    that scan plus Python ranking, as the Sims 4 backend calls it
* ``sims.recall_candidates``    the same for recall-candidate selection
* ``fts5.pair_rows``            prototype: FTS5 MATCH joined to the same pair filter, LIMIT 100
* ``core.get_for_agent``        ``EpisodicMemoryStore.get_for_agent`` (unbounded and limit=100)
* ``core.vector_search``        ``VectorMemoryStore.search`` brute-force KNN, 384 dimensions

Usage::

    python scripts/bench_recall.py                     # default sizes, human table
    python scripts/bench_recall.py --sizes 1000 10000 --repeat 30 --json out.json

Synthetic data and a fixed seed make runs comparable; absolute numbers depend on the machine,
so record the hardware alongside any result. The script never touches a real save database.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters" / "thesims4"))

from backend import empneon_state  # noqa: E402 - needs the adapter path added above
from empneon.core.memory.episodic import EpisodicMemoryStore  # noqa: E402
from empneon.core.memory.vector import VectorMemoryStore  # noqa: E402
from empneon.db.connection import open_db  # noqa: E402

AGENTS = 20  # SocietyBench ring size
HOT_PAIR = ("agent-00", "agent-01")
HOT_PAIR_SHARE = 0.05  # one long-running relationship holds this share of all events
DIMENSIONS = 384  # the hashed-vector size the Sims 4 adapter uses
TOPICS = (
    "garden key blue bench",
    "dinner reservation seven pm",
    "sister birthday party saturday",
    "library book overdue",
    "moving apartment boxes",
    "guitar lesson tuesday",
    "neighbor noisy dog",
    "road trip coast weekend",
    "painting studio rent",
    "coffee shop barista schedule",
)
FILLER = (
    "I was thinking about this earlier and it keeps coming back to me",
    "You always know what to say when things get complicated",
    "Let us talk about it properly when we both have time",
    "That reminds me of what happened last month at the market",
    "I did not expect the weather to turn like that today",
)
QUERIES = {
    "rare": "Do you remember the garden key",
    "common": "Do you remember what we talked about",
    "multi": "Remind me about the sister birthday party saturday dinner reservation",
}


def _description(rng: random.Random, speaker: str, listener: str, index: int) -> str:
    topic = rng.choice(TOPICS)
    message = f"{rng.choice(FILLER)}. About the {topic}, number {index}."
    return json.dumps(
        {
            "kind": "confirmed_interaction",
            "conversation_id": f"social-{index}",
            "speaker_id": speaker,
            "listener_id": listener,
            "message": message,
            "dialogue": f"{rng.choice(FILLER)}.",
            "facts": [
                {"actor_id": speaker, "statement": f"My {topic.split()[0]} matters to me."}
            ],
        }
    )


def seed(conn: sqlite3.Connection, total: int, rng: random.Random) -> None:
    now = int(time.time())
    agents = [f"agent-{i:02d}" for i in range(AGENTS)]
    conn.executemany(
        "INSERT INTO agents(id, name, created_at, updated_at) VALUES (?,?,?,?)",
        [(a, a, now, now) for a in agents],
    )
    events, participants = [], []
    for index in range(total):
        if rng.random() < HOT_PAIR_SHARE:
            speaker, listener = HOT_PAIR
        else:
            speaker, listener = rng.sample(agents, 2)
        event_id = f"event-{index:07d}"
        description = _description(rng, speaker, listener, index)
        events.append((event_id, description, None, now - total + index, now))
        participants.extend([(event_id, speaker), (event_id, listener)])
    conn.executemany(
        "INSERT INTO events(id, description, location, happened_at, created_at) VALUES (?,?,?,?,?)",
        events,
    )
    conn.executemany(
        "INSERT INTO event_participants(event_id, agent_id) VALUES (?,?)", participants
    )
    store = VectorMemoryStore(conn, DIMENSIONS, commit=False)
    for event in events:  # generate vectors one at a time to keep memory flat
        vector = [rng.uniform(-1, 1) for _ in range(DIMENSIONS)]
        store.upsert(event[0], vector, commit=False)
    conn.commit()


def build_fts(conn: sqlite3.Connection) -> float:
    """Create the FTS5 prototype index; return the build time in seconds."""
    started = time.perf_counter()
    conn.execute(
        "CREATE VIRTUAL TABLE events_fts USING fts5("
        "text, content='', tokenize='porter unicode61')"
    )
    conn.execute(
        "INSERT INTO events_fts(rowid, text)"
        " SELECT rowid, json_extract(description, '$.message') || ' ' ||"
        " json_extract(description, '$.dialogue') FROM events"
    )
    conn.commit()
    return time.perf_counter() - started


def fts_pair_rows(
    conn: sqlite3.Connection, actor: str, other: str, terms: set[str]
) -> list[sqlite3.Row]:
    match = " OR ".join(f'"{term}"' for term in sorted(terms))
    return conn.execute(
        "SELECT e.id, e.description, e.happened_at FROM events_fts f"
        " JOIN events e ON e.rowid = f.rowid"
        " WHERE events_fts MATCH ?"
        " AND json_extract(e.description, '$.speaker_id') IN (?, ?)"
        " AND json_extract(e.description, '$.listener_id') IN (?, ?)"
        " ORDER BY bm25(events_fts) LIMIT 100",
        (match, actor, other, actor, other),
    ).fetchall()


def timed(call: Callable[[], object], repeat: int) -> dict[str, float]:
    call()  # warm the page cache and statement cache
    samples = []
    for _ in range(repeat):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return {
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 2),
        "max_ms": round(samples[-1], 2),
    }


def measure(total: int, repeat: int, seed_value: int, directory: Path) -> dict[str, object]:
    rng = random.Random(seed_value)  # noqa: S311 - reproducible synthetic data, not security
    path = directory / f"recall-{total}.sqlite3"
    conn = open_db(path)
    started = time.perf_counter()
    seed(conn, total, rng)
    seed_seconds = time.perf_counter() - started
    fts_seconds = build_fts(conn)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    size_mb = round(path.stat().st_size / 1_048_576, 1)
    actor, other = HOT_PAIR
    cold_actor, cold_other = "agent-05", "agent-06"
    pair_events = int(
        conn.execute(
            "SELECT count(*) FROM events WHERE json_extract(description,'$.speaker_id') IN (?,?)"
            " AND json_extract(description,'$.listener_id') IN (?,?)",
            (actor, other, actor, other),
        ).fetchone()[0]
    )
    results: dict[str, dict[str, float]] = {}
    for name, query in QUERIES.items():
        terms = empneon_state._recall_terms(query)
        for label, (a, b) in (("hot", HOT_PAIR), ("cold", (cold_actor, cold_other))):
            tag = f"{name}.{label}"
            results[f"sims.recall_event_rows[{tag}]"] = timed(
                lambda a=a, b=b, t=terms: empneon_state._recall_event_rows(conn, a, b, t), repeat
            )
            results[f"fts5.pair_rows[{tag}]"] = timed(
                lambda a=a, b=b, t=terms: fts_pair_rows(conn, a, b, t), repeat
            )
            results[f"sims.recalled_memories[{tag}]"] = timed(
                lambda a=a, b=b, q=query: empneon_state.recalled_memories(conn, a, b, q), repeat
            )
            results[f"sims.recall_candidates[{tag}]"] = timed(
                lambda a=a, b=b, q=query: empneon_state.recall_candidates(conn, a, b, q), repeat
            )
    events = EpisodicMemoryStore(conn)
    results["core.get_for_agent[limit=100]"] = timed(
        lambda: events.get_for_agent(actor, 100), repeat
    )
    try:
        results["core.get_for_agent[unbounded]"] = timed(
            lambda: events.get_for_agent(actor), repeat
        )
    except sqlite3.OperationalError as error:
        results["core.get_for_agent[unbounded]"] = {
            "error": type(error).__name__
        }
    vectors = VectorMemoryStore(conn, DIMENSIONS, commit=False)
    probe = [rng.uniform(-1, 1) for _ in range(DIMENSIONS)]
    results["core.vector_search[k=10]"] = timed(lambda: vectors.search(probe, 10), repeat)
    results["core.vector_search[k=50]"] = timed(lambda: vectors.search(probe, 50), repeat)
    conn.close()
    return {
        "events": total,
        "hot_pair_events": pair_events,
        "database_mb": size_mb,
        "seed_seconds": round(seed_seconds, 1),
        "fts5_build_seconds": round(fts_seconds, 1),
        "results": results,
    }


def machine() -> dict[str, object]:
    model = ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    except OSError:
        model = platform.processor()
    return {
        "cpu": model,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
    }


def render(report: dict[str, object]) -> str:
    lines = [f"machine: {json.dumps(report['machine'])}", ""]
    for run in report["runs"]:  # type: ignore[attr-defined]
        lines.append(
            f"== {run['events']} events (hot pair {run['hot_pair_events']}, "
            f"db {run['database_mb']} MB, fts5 build {run['fts5_build_seconds']} s) =="
        )
        lines.append(f"{'measurement':<52}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}")
        for name, stats in run["results"].items():
            if "error" in stats:
                lines.append(f"{name:<52}{stats['error']}")
            else:
                lines.append(
                    f"{name:<52}{stats['p50_ms']:>10}{stats['p95_ms']:>10}{stats['max_ms']:>10}"
                )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 10_000, 50_000, 100_000])
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--json", type=Path, help="also write the raw report here")
    args = parser.parse_args()
    report: dict[str, object] = {"machine": machine(), "seed": args.seed, "runs": []}
    with tempfile.TemporaryDirectory() as directory:
        for size in args.sizes:
            print(f"seeding and measuring {size} events...", file=sys.stderr)
            report["runs"].append(measure(size, args.repeat, args.seed, Path(directory)))  # type: ignore[attr-defined]
    print(render(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
