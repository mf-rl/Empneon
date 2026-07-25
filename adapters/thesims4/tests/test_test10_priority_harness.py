import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import test10_priority_harness as harness  # noqa: E402


def test_evaluate_lifecycle_accepts_player_before_waiting_ambient() -> None:
    result = harness.evaluate_lifecycle(
        [
            {"actor_id": "empneon-test10-blocker", "state": "started"},
            {"actor_id": "empneon-test10-waiting", "state": "submitted"},
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "submitted",
            },
            {"actor_id": "empneon-test10-blocker", "state": "completed"},
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "started",
            },
            {"actor_id": "empneon-test10-waiting", "state": "started"},
        ],
        ("empneon-test10-blocker", "empneon-test10-waiting"),
    )

    assert result["passed"] is True
    assert result["reason"] == ""


def test_evaluate_lifecycle_rejects_ambient_started_before_player() -> None:
    result = harness.evaluate_lifecycle(
        [
            {"actor_id": "empneon-test10-blocker", "state": "started"},
            {"actor_id": "empneon-test10-waiting", "state": "submitted"},
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "submitted",
            },
            {"actor_id": "empneon-test10-waiting", "state": "started"},
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "started",
            },
        ],
        ("empneon-test10-blocker", "empneon-test10-waiting"),
    )

    assert result["passed"] is False
    assert result["reason"] == "waiting ambient work started before player work"


def test_evaluate_lifecycle_marks_cleared_backlog_inconclusive() -> None:
    result = harness.evaluate_lifecycle(
        [
            {"actor_id": "empneon-test10-blocker", "state": "started"},
            {"actor_id": "empneon-test10-waiting", "state": "submitted"},
            {"actor_id": "empneon-test10-waiting", "state": "started"},
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "submitted",
            },
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "started",
            },
        ],
        ("empneon-test10-blocker", "empneon-test10-waiting"),
    )

    assert result["passed"] is False
    assert result["inconclusive"] is True


def test_evaluate_lifecycle_rejects_missing_waiting_ambient_submission() -> None:
    result = harness.evaluate_lifecycle(
        [
            {"actor_id": "empneon-test10-blocker", "state": "started"},
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "submitted",
            },
            {
                "actor_id": "real-player",
                "event_type": "player_conversation",
                "state": "started",
            },
        ],
        ("empneon-test10-blocker", "empneon-test10-waiting"),
    )

    assert result["passed"] is False
    assert result["reason"] == "waiting ambient submission was not observed"


def test_collect_evidence_uses_real_queue_states(monkeypatch) -> None:
    run_id = "run123"
    blocker = "empneon-test10-run123-blocker"
    waiting = "empneon-test10-run123-waiting"
    recent = [
        {
            "actor_id": "old-player",
            "event_type": "player_conversation",
            "state": "submitted",
            "recorded_at": 1,
        },
        {
            "actor_id": "old-player",
            "event_type": "player_conversation",
            "state": "started",
            "recorded_at": 1,
        },
        {
            "actor_id": blocker,
            "event_type": "test10_blocker",
            "state": "started",
            "recorded_at": 11,
        },
        {
            "actor_id": waiting,
            "event_type": "critical_need",
            "state": "submitted",
            "recorded_at": 11,
        },
        {
            "actor_id": "real-player",
            "event_type": "player_conversation",
            "state": "submitted",
            "recorded_at": 11,
        },
        {
            "actor_id": blocker,
            "event_type": "critical_need",
            "state": "completed",
            "recorded_at": 11,
        },
        {
            "actor_id": "real-player",
            "event_type": "player_conversation",
            "state": "started",
            "recorded_at": 11,
        },
        {
            "actor_id": waiting,
            "event_type": "critical_need",
            "state": "started",
            "recorded_at": 11,
        },
        {
            "actor_id": waiting,
            "event_type": "critical_need",
            "state": "completed",
            "recorded_at": 11,
        },
    ]
    snapshots = iter(
        [
            {
                "worker_limit": 1,
                "running": [{"actor_id": blocker}],
                "waiting": [
                    {"actor_id": waiting},
                    {"actor_id": "real-player"},
                ],
                "recent": recent[:5],
            },
            {
                "worker_limit": 1,
                "running": [],
                "waiting": [],
                "recent": recent,
            },
        ]
    )
    gate_calls = []

    def fake_request(method, url, payload=None, timeout=120):
        del timeout
        if url.endswith("/health"):
            return {"status": "ok", "active_agent_limit": 1}
        if url.endswith("/diagnostics/cognition-queue/test10-gate"):
            gate_calls.append(payload["action"])
            if payload["action"] == "arm":
                return {
                    "status": "armed",
                    "actor_ids": {"blocker": blocker, "waiting": waiting},
                }
            return {"status": "released"}
        if url.endswith("/diagnostics/cognition-queue"):
            return next(snapshots)
        raise AssertionError((method, url))

    monkeypatch.setattr(harness, "request_json", fake_request)
    monkeypatch.setattr(harness.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(harness.time, "time", lambda: 10)
    prompts = []

    report = harness.collect_evidence(
        "http://example.test",
        setup_timeout=1,
        completion_timeout=1,
        prompt=lambda message: prompts.append(message),
        run_id=run_id,
    )

    assert report["status"] == "passed"
    assert report["evaluation"]["passed"] is True
    assert report["actor_ids"] == [blocker, waiting]
    assert gate_calls == ["arm", "release"]
    assert len(prompts) == 2
    assert "do not submit" in prompts[0].lower()
    assert "submit" in prompts[1].lower()


def test_collect_evidence_releases_gate_when_player_is_not_observed(
    monkeypatch,
) -> None:
    gate_calls = []

    def fake_request(_method, url, payload=None, timeout=120):
        del timeout
        if url.endswith("/health"):
            return {"status": "ok", "active_agent_limit": 1}
        if url.endswith("/diagnostics/cognition-queue/test10-gate"):
            gate_calls.append(payload["action"])
            return {
                "status": payload["action"],
                "actor_ids": {
                    "blocker": "empneon-test10-timeout-blocker",
                    "waiting": "empneon-test10-timeout-waiting",
                },
            }
        raise AssertionError(url)

    monkeypatch.setattr(harness, "request_json", fake_request)

    report = harness.collect_evidence(
        "http://example.test",
        completion_timeout=0,
        prompt=lambda _message: "",
        run_id="timeout",
    )

    assert report["status"] == "inconclusive"
    assert gate_calls == ["arm", "release"]
