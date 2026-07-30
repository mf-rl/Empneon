import contextlib
import logging
import re
import threading
import time
from collections import deque

from empneon.core.contracts import CognitiveRequest, WorldEvent
from empneon.core.scheduler.priority import PriorityScheduler, RequestDeadlineExceeded

LOG = logging.getLogger("ai_sims.agent_manager")


class CognitionQueue:
    def __init__(
        self,
        workers,
        max_queue_size,
        clock=time.time,
        log_info=LOG.info,
    ):
        self._worker_limit = max(1, int(workers))
        self._scheduler = PriorityScheduler(max_queue_size)
        self._jobs = {}
        self._states = {}
        self._recent = deque(maxlen=64)
        self._condition = threading.Condition()
        self._workers_started = False
        self._clock = clock
        self._log_info = log_info

    def __len__(self):
        return len(self._scheduler)

    def _request_state(self, request, state):
        return {
            "request_id": request.id,
            "actor_id": request.agent_id,
            "event_type": request.event.type,
            "urgency": request.urgency,
            "state": state,
            "submitted_at": self._clock(),
            "started_at": None,
        }

    def _record(self, item, state):
        record = dict(item, state=state, recorded_at=self._clock())
        self._recent.append(record)
        try:
            self._log_info(
                "cognition request %s id=%s actor=%s event=%s urgency=%s queue_depth=%s",
                state,
                record["request_id"],
                record["actor_id"],
                record["event_type"],
                record["urgency"],
                len(self._scheduler),
            )
        except Exception:
            pass

    def snapshot(self):
        with self._condition:
            states = [dict(item) for item in self._states.values()]
            return {
                "worker_limit": self._worker_limit,
                "running": [item for item in states if item["state"] == "running"],
                "waiting": [item for item in states if item["state"] == "waiting"],
                "recent": [dict(item) for item in self._recent],
            }

    def run(self, request, work):
        self._start_workers()
        job = {"work": work, "done": threading.Event(), "result": None, "error": None}
        with self._condition:
            self._jobs[request.id] = job
            state = self._request_state(request, "waiting")
            self._states[request.id] = state
            try:
                self._scheduler.submit(request)
            except Exception:
                self._jobs.pop(request.id, None)
                self._states.pop(request.id, None)
                raise
            self._record(state, "submitted")
            self._condition.notify()
        if not job["done"].wait(request.deadline_ms / 1000):
            with self._condition:
                self._jobs.pop(request.id, None)
                state = self._states.pop(request.id, None)
                if state is not None:
                    self._record(state, "timed_out")
            raise RequestDeadlineExceeded("cognitive request deadline exceeded")
        if job["error"] is not None:
            raise job["error"]
        return job["result"]

    def _start_workers(self):
        with self._condition:
            if self._workers_started:
                return
            self._workers_started = True
            for index in range(self._worker_limit):
                threading.Thread(
                    target=self._work,
                    name=f"empneon-cognition-{index}",
                    daemon=True,
                ).start()

    def _work(self):
        while True:
            with self._condition:
                while len(self._scheduler) == 0:
                    self._condition.wait()
                try:
                    request = self._scheduler.pop()
                except RequestDeadlineExceeded:
                    continue
                job = self._jobs.get(request.id)
            if job is None:
                continue
            with self._condition:
                state = self._states.get(request.id)
                if state is not None:
                    state["state"] = "running"
                    state["started_at"] = self._clock()
                    self._record(state, "started")
            try:
                job["result"] = job["work"]()
            except Exception as exc:
                job["error"] = exc
            finally:
                with self._condition:
                    self._jobs.pop(request.id, None)
                    state = self._states.pop(request.id, None)
                    if state is not None:
                        self._record(
                            state,
                            "failed" if job["error"] is not None else "completed",
                        )
                job["done"].set()


class Test10QueueGate:
    def __init__(
        self,
        queue,
        timeout_seconds=60,
        monotonic=time.monotonic,
        sleep=time.sleep,
        log_exception=LOG.exception,
    ):
        self._queue = queue
        self._timeout_seconds = max(1, int(timeout_seconds))
        self._lock = threading.Lock()
        self._active = None
        self._monotonic = monotonic
        self._sleep = sleep
        self._log_exception = log_exception

    def _wait_for(self, actor_id, state):
        deadline = self._monotonic() + 2
        while self._monotonic() < deadline:
            if any(item["actor_id"] == actor_id for item in self._queue.snapshot()[state]):
                return True
            self._sleep(0.005)
        return False

    def _run_safely(self, request, work):
        try:
            self._queue.run(request, work)
        except Exception:
            self._log_exception("Test 10 diagnostic queue work failed")

    def arm(self, run_id):
        run_id = str(run_id or "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", run_id):
            raise ValueError("valid Test 10 run_id is required")
        release = threading.Event()
        blocker_id = f"empneon-test10-{run_id}-blocker"
        waiting_id = f"empneon-test10-{run_id}-waiting"
        with self._lock:
            if self._active is not None:
                raise ValueError("a Test 10 queue gate is already active")
            self._active = {"run_id": run_id, "release": release}

        blocker = CognitiveRequest(
            blocker_id,
            1,
            WorldEvent("test10_blocker", (blocker_id,)),
            urgency=0.0,
            deadline_ms=(self._timeout_seconds + 5) * 1000,
        )

        def hold_worker():
            try:
                self._queue.run(
                    blocker,
                    lambda: release.wait(self._timeout_seconds),
                )
            finally:
                with self._lock:
                    if self._active and self._active["run_id"] == run_id:
                        self._active = None

        threading.Thread(target=hold_worker, daemon=True).start()
        if not self._wait_for(blocker_id, "running"):
            release.set()
            raise RuntimeError("Test 10 blocker did not start")

        waiting = CognitiveRequest(
            waiting_id,
            1,
            WorldEvent("critical_need", (waiting_id,)),
            urgency=0.85,
            deadline_ms=(self._timeout_seconds + 5) * 1000,
        )
        threading.Thread(
            target=self._run_safely,
            args=(waiting, lambda: None),
            daemon=True,
        ).start()
        if not self._wait_for(waiting_id, "waiting"):
            release.set()
            raise RuntimeError("Test 10 ambient request did not wait")
        return {"blocker": blocker_id, "waiting": waiting_id}

    def release(self, run_id):
        with self._lock:
            if self._active is None or self._active["run_id"] != str(run_id or ""):
                raise ValueError("matching active Test 10 run_id is required")
            self._active["release"].set()
        return {"run_id": str(run_id), "released": True}


class AgentManager:
    def __init__(self, limit, profile_lookup, clock, log_info):
        self.limit = max(1, int(limit or 1))
        self._profile_lookup = profile_lookup
        self._clock = clock
        self._log_info = log_info
        self._lock = threading.RLock()
        self._active = {}

    def wake_agent(self, sim, reason="request", priority=3, timeout=None):
        profile = self._profile_lookup(sim)
        sid = profile["id"]
        with self._lock:
            if sid in self._active:
                self._active[sid]["refs"] += 1
                self._active[sid]["last_reason"] = reason
                self._log_info(
                    "agent reused sim=%s reason=%s refs=%s",
                    sid,
                    reason,
                    self._active[sid]["refs"],
                )
                return profile

        with self._lock:
            self._active[sid] = {
                "sim_id": sid,
                "name": profile["name"],
                "state": "active",
                "priority": int(priority or 3),
                "refs": 1,
                "woke_at": self._clock(),
                "last_reason": reason,
            }
        self._log_info(
            "agent woke sim=%s name=%s reason=%s priority=%s",
            sid,
            profile["name"],
            reason,
            priority,
        )
        return profile

    def sleep_agent(self, sim_id_value, reason="complete"):
        release = False
        with self._lock:
            active = self._active.get(str(sim_id_value))
            if not active:
                return False
            active["refs"] -= 1
            if active["refs"] <= 0:
                self._active.pop(str(sim_id_value), None)
                release = True
        if release:
            self._log_info("agent slept sim=%s reason=%s", sim_id_value, reason)
        return True

    @contextlib.contextmanager
    def session(self, sim, reason="request", priority=3):
        profile = self.wake_agent(sim, reason=reason, priority=priority)
        try:
            yield profile
        finally:
            self.sleep_agent(profile["id"], reason="session complete")

    def get_active_agents(self):
        with self._lock:
            return [dict(value) for value in self._active.values()]
