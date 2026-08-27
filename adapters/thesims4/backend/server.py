import ipaddress
import json
import secrets
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class EmpneonHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    resolve = None

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length > self.resolve("MAX_REQUEST_BODY_BYTES"):
            raise ValueError("request body too large")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def is_authorized(self):
        return not self.resolve("API_TOKEN") or secrets.compare_digest(
            str(self.headers.get("X-Empneon-Token") or ""),
            self.resolve("API_TOKEN"),
        )

    def do_GET(self):
        if not self.is_authorized():
            self.send_json(401, {"error": "unauthorized"})
            return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path.startswith("/diagnostics/") or parsed.path == "/identity/export":
            self._get_diagnostic_response(parsed.path, query)
            return
        if parsed.path == "/health":
            self.send_json(200, self._build_health_payload())
            return
        handler = self._GET_ROUTES.get(parsed.path)
        if handler:
            handler(self, query)
            return
        self.send_json(404, {"error": "not found"})

    def _get_diagnostic_response(self, path, query):
        try:
            self._send_diagnostic(path, query)
        except self.resolve("DiagnosticInputError") as exc:
            self.send_json(400, {"error": str(exc)})
        except self.resolve("DiagnosticNotFound") as exc:
            self.send_json(404, {"error": str(exc)})
        except Exception:
            self.resolve("LOG").exception("diagnostic request failed")
            self.send_json(500, {"error": "diagnostic request failed"})

    def _build_health_payload(self):
        small = self.resolve("task_model_config")("small")
        large = self.resolve("task_model_config")("large")
        return {
            "status": "ok",
            "model": self.resolve("configured_model")(),
            "provider": self.resolve("PRIMARY_PROVIDER"),
            "llm_base_url": large.get("endpoint"),
            "models": {
                "small": {
                    "provider": small.get("name"),
                    "model": self.resolve("configured_model")("small"),
                },
                "large": {
                    "provider": large.get("name"),
                    "model": self.resolve("configured_model")("large"),
                },
            },
            "memory_db": self.resolve("CORE_DB_PATH"),
            "legacy_import_db": self.resolve("ACTIVE_DB_PATH") or self.resolve("DB_PATH"),
            "preserve_memory_only_on_game_save": self.resolve(
                "PRESERVE_MEMORY_ONLY_ON_GAME_SAVE"
            ),
            "active_agent_limit": self.resolve("ACTIVE_AGENT_LIMIT"),
            "active_agents": self.resolve("AGENTS").get_active_agents(),
        }

    def _get_agents_active(self, query):
        self.send_json(
            200,
            {"active_agents": self.resolve("AGENTS").get_active_agents()},
        )

    def _get_profiles(self, query):
        self.send_json(
            200,
            {
                "profiles": self.resolve("list_profiles")(
                    limit=int(query.get("limit", [100])[0])
                )
            },
        )

    def _get_profile(self, query):
        sim_id_value = query.get("sim_id", [""])[0]
        self.send_json(
            200,
            {"profile": self.resolve("get_profile")(sim_id_value)},
        )

    def _get_memories(self, query):
        speaker_id = query.get("speaker_id", query.get("sim_id", [""]))[0]
        listener_id = query.get("listener_id", query.get("target_id", [""]))[0]
        if listener_id:
            memories = self.resolve("memories_for_pair")(
                speaker_id,
                listener_id,
                limit=int(query.get("limit", [20])[0]),
            )
            summary = self.resolve("memory_summary")(speaker_id, listener_id)
        else:
            memories = self.resolve("memories_for_sim")(
                speaker_id,
                limit=int(query.get("limit", [20])[0]),
            )
            summary = {"summary": "", "updated_at": 0}
        self.send_json(200, {"memories": memories, "summary": summary})

    def _get_relationship(self, query):
        sim_id_value = query.get("sim_id", [""])[0]
        target_id_value = query.get("target_id", [""])[0]
        self.send_json(
            200,
            {
                "relationship": self.resolve("get_relationship_diagnostic")(
                    sim_id_value, target_id_value
                )
            },
        )

    def _get_emotion(self, query):
        sim_id_value = query.get("sim_id", [""])[0]
        self.send_json(
            200,
            {"emotion": self.resolve("get_emotion")(sim_id_value)},
        )

    def _get_voice(self, query):
        sim_id_value = query.get("sim_id", [""])[0]
        self.send_json(
            200,
            {"voice": self.resolve("voice_profile")(sim_id_value)},
        )

    _GET_ROUTES = {
        "/agents/active": _get_agents_active,
        "/profiles": _get_profiles,
        "/profile": _get_profile,
        "/memories": _get_memories,
        "/relationship": _get_relationship,
        "/emotion": _get_emotion,
        "/voice": _get_voice,
    }

    def _send_diagnostic(self, path, query):
        if path == "/diagnostics/cognition-queue":
            self.send_json(200, self.resolve("COGNITION_QUEUE").snapshot())
            return
        if path == "/diagnostics/migration":
            self.send_json(200, self._diagnostic_migration_status())
            return
        if path == "/diagnostics/usage" and not str(query.get("sim_id", [""])[0]).strip():
            self.send_json(200, self._diagnostic_usage_totals())
            return
        self.send_json(200, self._diagnostic_for_identifier(path, query))

    def _diagnostic_migration_status(self):
        body = self.resolve("MIGRATION_STATUS").as_dict()
        with self.resolve("db_session")(self.resolve("CORE_DB_PATH")) as conn:
            body["completion_markers"] = [
                document.key
                for document in self.resolve("DocumentMemoryStore")(conn).list(
                    "thesims4.migration"
                )
            ]
        return body

    def _diagnostic_usage_totals(self):
        with self.resolve("db_session")(self.resolve("CORE_DB_PATH")) as conn:
            return self.resolve("UsageStore")(conn).telemetry()

    def _diagnostic_for_identifier(self, path, query):
        name = "decision_id" if path == "/diagnostics/replay" else "sim_id"
        identifier = self.resolve("diagnostic_identifier")(query, name)
        with self.resolve("db_session")(self.resolve("CORE_DB_PATH")) as conn:
            return self._diagnostic_body(conn, path, identifier)

    def _diagnostic_body(self, conn, path, identifier):
        if path == "/diagnostics/replay":
            try:
                return self.resolve("replay_action_record")(conn, identifier)
            except ValueError as exc:
                raise self.resolve("DiagnosticNotFound")(str(exc)) from exc
        if self.resolve("AgentStore")(conn).get(identifier) is None:
            raise self.resolve("DiagnosticNotFound")("Sim does not exist")
        if path == "/diagnostics/sim":
            return self.resolve("empneon_state").sim_diagnostics(conn, identifier)
        if path == "/diagnostics/timeline":
            return self.resolve("sims_timeline")(conn, identifier)
        if path == "/diagnostics/usage":
            return self.resolve("UsageStore")(conn).telemetry(identifier)
        if path == "/identity/export":
            return self.resolve("empneon_state").export_identity(conn, identifier)
        raise self.resolve("DiagnosticNotFound")("diagnostic route does not exist")

    def do_POST(self):
        if not self.is_authorized():
            self.send_json(401, {"error": "unauthorized"})
            return
        try:
            payload = self.read_json()
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/identity/import":
                self._post_identity_import(payload)
                return
            if parsed.path == "/diagnostics/cognition-queue/test10-gate":
                self._post_test10_gate(payload)
                return
            session_id = payload.get("_empneon_session_id")
            save_slot_id = payload.get("_empneon_save_slot_id") or ""
            if parsed.path == "/game-session/start":
                self.send_json(
                    200,
                    self.resolve("start_memory_session")(session_id, save_slot_id),
                )
                return
            if parsed.path == "/game-session/save":
                self.send_json(
                    200,
                    self.resolve("save_memory_session")(session_id, save_slot_id),
                )
                return
            if session_id:
                self.resolve("start_memory_session")(session_id, save_slot_id)
            # /chat and /conversation are aliases for the same handler
            handler = self._POST_ROUTES.get(
                "/chat" if parsed.path == "/conversation" else parsed.path
            )
            if handler:
                handler(self, payload)
                return
            self.send_json(404, {"error": "not found"})
        except Exception:
            self.resolve("LOG").exception("request failed")
            self.send_json(500, {"error": "request failed"})

    def _post_identity_import(self, payload):
        if not isinstance(payload, dict):
            self.send_json(400, {"error": "identity must be a JSON object"})
            return
        try:
            with self.resolve("db_session")(self.resolve("CORE_DB_PATH")) as conn:
                agent = self.resolve("empneon_state").import_identity(conn, payload)
        except (KeyError, TypeError, ValueError) as exc:
            self.send_json(400, {"error": str(exc)})
            return
        self.send_json(
            200,
            {"agent": {"id": agent.id, "name": agent.name}},
        )

    def _post_test10_gate(self, payload):
        try:
            loopback = ipaddress.ip_address(self.client_address[0]).is_loopback
        except (AttributeError, IndexError, ValueError):
            loopback = False
        if not loopback:
            self.send_json(403, {"error": "loopback access required"})
            return
        action = str(payload.get("action") or "")
        run_id = str(payload.get("run_id") or "")
        try:
            if action == "arm":
                actor_ids = self.resolve("TEST10_QUEUE_GATE").arm(run_id)
                self.send_json(
                    200,
                    {
                        "status": "armed",
                        "run_id": run_id,
                        "actor_ids": actor_ids,
                    },
                )
            elif action == "release":
                self.resolve("TEST10_QUEUE_GATE").release(run_id)
                self.send_json(
                    200,
                    {"status": "released", "run_id": run_id},
                )
            else:
                self.send_json(
                    400,
                    {"error": "action must be arm or release"},
                )
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})

    def _post_chat(self, payload):
        if not payload.get("message"):
            self.send_json(400, {"error": "message is required"})
            return
        self.send_json(200, self.resolve("chat")(payload))

    def _post_director(self, payload):
        self.send_json(200, self.resolve("director")(payload))

    def _post_autonomous(self, payload):
        self.send_json(200, self.resolve("autonomous_action")(payload))

    def _post_action_result(self, payload):
        try:
            self.send_json(200, self.resolve("confirm_action")(payload))
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})

    def _post_dialogue_result(self, payload):
        try:
            self.send_json(
                200,
                self.resolve("confirm_dialogue_delivery")(payload),
            )
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})

    def _post_agent_wake(self, payload):
        sim = payload.get("sim") or payload.get("speaker") or payload
        profile = self.resolve("AGENTS").wake_agent(
            sim,
            reason=payload.get("reason") or "manual",
            priority=payload.get("priority") or 3,
        )
        self.send_json(
            200,
            {
                "profile": profile,
                "active_agents": self.resolve("AGENTS").get_active_agents(),
            },
        )

    def _post_agent_sleep(self, payload):
        sim_id_value = str(payload.get("sim_id") or payload.get("id") or "")
        self.send_json(
            200,
            {
                "slept": self.resolve("AGENTS").sleep_agent(sim_id_value),
                "active_agents": self.resolve("AGENTS").get_active_agents(),
            },
        )

    def _post_profile(self, payload):
        sim = payload.get("sim") or payload
        self.send_json(
            200,
            {"profile": self.resolve("upsert_profile")(sim)},
        )

    def _post_memory(self, payload):
        self.resolve("add_memory")(
            str(payload.get("sim_id") or payload.get("speaker_id") or ""),
            str(payload.get("target_id") or payload.get("listener_id") or ""),
            payload.get("summary") or payload.get("event") or "",
            payload.get("importance", 0.5),
            emotion=payload.get("emotion") or "",
            category=payload.get("category") or "",
            topic=payload.get("topic") or "",
            location=payload.get("location") or "",
        )
        self.send_json(200, {"status": "ok"})

    def _post_relationship(self, payload):
        sim_id_value = str(payload.get("sim_id") or "")
        target_id_value = str(payload.get("target_id") or "")
        self.send_json(
            200,
            {
                "relationship": self.resolve("save_relationship")(
                    sim_id_value,
                    target_id_value,
                    payload.get("relationship") or payload,
                )
            },
        )

    def _post_emotion(self, payload):
        sim_id_value = str(payload.get("sim_id") or "")
        self.send_json(
            200,
            {
                "emotion": self.resolve("save_emotion")(
                    sim_id_value,
                    payload.get("emotion") or payload,
                )
            },
        )

    def _post_voice(self, payload):
        sim_id_value = str(payload.get("sim_id") or "")
        self.send_json(
            200,
            {
                "voice": self.resolve("save_voice_profile")(
                    sim_id_value,
                    payload.get("voice") or payload,
                )
            },
        )

    def _post_tts(self, payload):
        self.send_json(200, self.resolve("tts_generate")(payload))

    _POST_ROUTES = {
        "/chat": _post_chat,
        "/director": _post_director,
        "/autonomous": _post_autonomous,
        "/action-result": _post_action_result,
        "/dialogue-result": _post_dialogue_result,
        "/agent/wake": _post_agent_wake,
        "/agent/sleep": _post_agent_sleep,
        "/profile": _post_profile,
        "/memory": _post_memory,
        "/relationship": _post_relationship,
        "/emotion": _post_emotion,
        "/voice": _post_voice,
        "/tts": _post_tts,
    }
