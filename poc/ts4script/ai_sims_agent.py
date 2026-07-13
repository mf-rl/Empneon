import json
import os
import traceback
import threading
import urllib.parse

import alarms
import clock
import services
import sims4.commands
import zone


BACKEND_URL = "http://127.0.0.1:8765"
AUTONOMY_INTERVAL_SIM_MINUTES = 30
AVAILABLE_ACTIONS = [
    "friendly_chat",
    "funny_chat",
    "romantic_chat",
    "awkward_chat",
    "angry_chat",
    "sad_chat",
    "apologize",
    "argue",
    "flirt",
    "laugh",
]
_AUTONOMY_ALARM = None
_AUTONOMY_RESPONSE_ALARM = None
_AUTONOMY_CURSOR = 0
_AUTONOMY_IN_FLIGHT = False
_AUTONOMY_RESPONSES = []
_AUTONOMY_RESPONSES_LOCK = threading.Lock()


def write_marker(text):
    try:
        base = os.path.join(os.path.expanduser("~"), "Documents", "Electronic Arts", "The Sims 4")
        path = os.path.join(base, "ai_sims_agent_loaded.txt")
        handle = open(path, "a")
        try:
            handle.write(str(text) + "\n")
        finally:
            handle.close()
    except Exception:
        pass


write_marker("AI Sims Agent imported")


def command(name):
    return sims4.commands.Command(name, command_type=sims4.commands.CommandType.Live)


def out(connection, text):
    sims4.commands.CheatOutput(connection)(str(text))


def active_sim(connection):
    client = services.client_manager().get(connection)
    return getattr(client, "active_sim", None)


def text_value(value, default="unknown"):
    try:
        if callable(value):
            value = value()
        if value:
            return str(value)
    except Exception:
        pass
    return default


def sim_full_name(sim_info):
    name = getattr(sim_info, "full_name", None)
    if name:
        return str(name)
    first = text_value(getattr(sim_info, "first_name", None), "")
    last = text_value(getattr(sim_info, "last_name", None), "")
    return (first + " " + last).strip() or "Unknown Sim"


def clean_name(text):
    return " ".join(str(text or "").strip().lower().split())


def short_trait_name(trait):
    for attr in ("__name__", "name", "trait_type", "guid64"):
        try:
            value = getattr(trait, attr, None)
            if callable(value):
                value = value()
            text = str(value or "").strip()
            if text and "tokens {" not in text.lower():
                return text[:80]
        except Exception:
            pass
    return ""


def sim_traits(sim_info):
    tracker = getattr(sim_info, "trait_tracker", None)
    traits = []
    try:
        equipped = getattr(tracker, "equipped_traits", None)
        if callable(equipped):
            equipped = equipped()
        for trait in equipped or []:
            name = short_trait_name(trait)
            if name:
                traits.append(name)
    except Exception:
        pass
    return [trait for trait in traits if trait]


def sim_mood(sim_info):
    try:
        mood = sim_info.get_mood()
        display_name = getattr(mood, "display_name", None)
        if callable(display_name):
            return str(display_name(sim_info))
        return str(display_name or mood)
    except Exception:
        return "unknown"


def sim_info_payload(sim_info):
    return {
        "id": str(getattr(sim_info, "sim_id", sim_full_name(sim_info))),
        "name": sim_full_name(sim_info),
        "traits": sim_traits(sim_info),
        "current_mood": sim_mood(sim_info),
        "career": "unknown",
        "skills": {},
    }


def sim_payload(sim):
    return sim_info_payload(sim.sim_info)


def current_location():
    try:
        zone = services.current_zone()
        lot = getattr(zone, "lot", None)
        lot_name = text_value(getattr(lot, "name", None), "")
        if lot_name:
            return lot_name
        zone_id = getattr(zone, "id", None) or getattr(zone, "zone_id", None)
        if zone_id:
            return "zone:{}".format(zone_id)
    except Exception:
        pass
    return "unknown"


def relationship_payload(source_info, target_info):
    # ponytail: aggregate score only; add tuned tracks when action mapping needs them.
    result = {"friendship": 0, "romance": 0, "trust": 50, "resentment": 0}
    if target_info is None:
        return result
    tracker = getattr(source_info, "relationship_tracker", None)
    target_id = getattr(target_info, "sim_id", None)
    for method_name in ("get_relationship_score", "get_relationship_score_by_sim_id"):
        method = getattr(tracker, method_name, None)
        if not callable(method):
            continue
        for target in (target_info, target_id):
            if target is None:
                continue
            try:
                raw_score = float(method(target))
                result["friendship"] = int(max(0, min(100, round((raw_score + 100) / 2))))
                result["raw_score"] = raw_score
                return result
            except Exception:
                pass
    return result


def iter_sim_infos():
    try:
        manager = services.sim_info_manager()
    except Exception:
        return
    for attr in ("get_all", "values"):
        try:
            source = getattr(manager, attr, None)
            if not source:
                continue
            items = source() if callable(source) else source
            if isinstance(items, dict):
                items = items.values()
            for item in items or []:
                yield item
            return
        except Exception:
            pass
    for attr in ("_objects", "objects"):
        try:
            items = getattr(manager, attr, None)
            if isinstance(items, dict):
                items = items.values()
            for item in items or []:
                yield item
            return
        except Exception:
            pass


def instanced_npc_infos():
    result = []
    for sim_info in iter_sim_infos() or []:
        try:
            sim = sim_info.get_sim_instance()
            if sim is not None and not sim.is_selectable:
                result.append(sim_info)
        except Exception:
            pass
    return result


def autonomous_tick(_alarm_handle):
    global _AUTONOMY_CURSOR, _AUTONOMY_IN_FLIGHT
    if _AUTONOMY_IN_FLIGHT:
        return
    candidates = instanced_npc_infos()
    if len(candidates) < 2:
        return
    speaker = candidates[_AUTONOMY_CURSOR % len(candidates)]
    listener = candidates[(_AUTONOMY_CURSOR + 1) % len(candidates)]
    _AUTONOMY_CURSOR = (_AUTONOMY_CURSOR + 1) % len(candidates)
    payload = {
        "speaker": sim_info_payload(speaker),
        "listener": sim_info_payload(listener),
        "relationship": relationship_payload(speaker, listener),
        "location": current_location(),
        "event": {"type": "autonomous_social", "source": "sim_alarm"},
        "available_actions": AVAILABLE_ACTIONS,
    }
    _AUTONOMY_IN_FLIGHT = True

    def worker():
        try:
            data = post_json("/autonomous", payload)
            with _AUTONOMY_RESPONSES_LOCK:
                _AUTONOMY_RESPONSES.append((payload, data))
        except Exception:
            global _AUTONOMY_IN_FLIGHT
            _AUTONOMY_IN_FLIGHT = False
            write_marker(traceback.format_exc())

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()


def process_autonomy_responses(_alarm_handle):
    with _AUTONOMY_RESPONSES_LOCK:
        item = _AUTONOMY_RESPONSES.pop(0) if _AUTONOMY_RESPONSES else None
    if item is None:
        return
    payload, data = item
    execute_sims_action(payload, data)


def execute_sims_action(payload, data):
    decision_id = str(data.get("decision_id") or "")
    action = str(data.get("suggested_action") or "")
    speaker_id = str(payload["speaker"]["id"])
    listener_id = str(payload["listener"]["id"])
    try:
        actor_info = find_sim_info_by_id(speaker_id)
        target_info = find_sim_info_by_id(listener_id)
        actor = actor_info.get_sim_instance() if actor_info is not None else None
        target = target_info.get_sim_instance() if target_info is not None else None
        if actor is None or target is None:
            raise RuntimeError("actor or target left the active zone")
        affordance = find_action_affordance(action)
        if affordance is None:
            raise RuntimeError("no loaded tuning for {}".format(action))

        from interactions.context import InteractionContext, QueueInsertStrategy
        from interactions.priority import Priority

        context = InteractionContext(
            actor,
            InteractionContext.SOURCE_SCRIPT,
            Priority.High,
            insert_strategy=QueueInsertStrategy.NEXT,
        )
        enqueue_result = None
        for aop in target.potential_interactions(context):
            if getattr(aop, "affordance", None) is affordance:
                enqueue_result = aop.test_and_execute(context)
                break
        interaction = getattr(enqueue_result, "interaction", None)
        if not enqueue_result or interaction is None:
            raise RuntimeError(
                "game rejected potential interaction: {}".format(
                    getattr(affordance, "__name__", affordance)
                )
            )
        callback = getattr(interaction, "register_on_finishing_callback", None)
        if not callable(callback):
            raise RuntimeError("game interaction has no completion callback")

        def finished(completed_interaction):
            finishing_type = str(getattr(completed_interaction, "finishing_type", ""))
            succeeded = finishing_type.lower().endswith("natural")
            changes = []
            if succeeded:
                before = payload.get("relationship") or {}
                after = relationship_payload(actor_info, target_info)
                for key in ("friendship", "romance"):
                    delta = int(after.get(key, 0)) - int(before.get(key, 0))
                    if delta:
                        changes.append(
                            {
                                "path": "relationship." + key,
                                "operation": "increment",
                                "value": delta,
                            }
                        )
            report_action_result(
                decision_id,
                action,
                "succeeded" if succeeded else "failed",
                None if succeeded else finishing_type or "interaction canceled",
                changes,
            )

        callback(finished)
        write_marker(
            "queued {} -> {}: {}".format(
                payload["speaker"]["name"], payload["listener"]["name"], action
            )
        )
    except Exception as exc:
        report_action_result(decision_id, action, "failed", str(exc), [])


def report_action_result(decision_id, action, status, reason=None, changes=None):
    body = {
        "decision_id": decision_id,
        "action": action,
        "status": status,
        "reason": reason,
        "changes": changes or [],
    }

    def worker():
        global _AUTONOMY_IN_FLIGHT
        try:
            post_json("/action-result", body, timeout=10)
            write_marker("confirmed {}: {} ({})".format(decision_id, action, status))
        except Exception:
            write_marker(traceback.format_exc())
        finally:
            _AUTONOMY_IN_FLIGHT = False

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()


def find_sim_info_by_id(sim_id):
    target = str(sim_id)
    for sim_info in iter_sim_infos() or []:
        if str(getattr(sim_info, "sim_id", "")) == target:
            return sim_info
    return None


def find_action_affordance(action):
    if action != "friendly_chat":
        return None
    import sims4.resources

    manager = services.get_instance_manager(sims4.resources.Types.INTERACTION)
    for affordance in loaded_interaction_tunings(manager):
        name = str(getattr(affordance, "__name__", ""))
        if name == "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn":
            return affordance
    return None


def loaded_interaction_tunings(manager=None):
    if manager is None:
        import sims4.resources

        manager = services.get_instance_manager(sims4.resources.Types.INTERACTION)
    tunings = getattr(manager, "types", None) or getattr(manager, "_tuned_classes", {})
    return tuple(tunings.values())


def social_tuning_names(query=""):
    names = {
        str(getattr(affordance, "__name__", ""))
        for affordance in loaded_interaction_tunings()
    }
    query = str(query or "").strip().lower()
    filtered = [
        name
        for name in names
        if ("social" in name.lower() or "chat" in name.lower())
        and (not query or query in name.lower())
    ]
    return sorted(filtered, key=lambda name: (":" in name, name.lower()))


def start_autonomy(zone_instance):
    global _AUTONOMY_ALARM, _AUTONOMY_RESPONSE_ALARM
    if _AUTONOMY_ALARM is not None:
        alarms.cancel_alarm(_AUTONOMY_ALARM)
    if _AUTONOMY_RESPONSE_ALARM is not None:
        alarms.cancel_alarm(_AUTONOMY_RESPONSE_ALARM)
    _AUTONOMY_ALARM = alarms.add_alarm(
        zone_instance,
        clock.interval_in_sim_minutes(AUTONOMY_INTERVAL_SIM_MINUTES),
        autonomous_tick,
        repeating=True,
    )
    _AUTONOMY_RESPONSE_ALARM = alarms.add_alarm_real_time(
        zone_instance,
        clock.interval_in_real_seconds(1),
        process_autonomy_responses,
        repeating=True,
    )


_ORIGINAL_ZONE_READY = zone.Zone.on_loading_screen_animation_finished


def _on_zone_ready(self, *args, **kwargs):
    result = _ORIGINAL_ZONE_READY(self, *args, **kwargs)
    start_autonomy(self)
    return result


zone.Zone.on_loading_screen_animation_finished = _on_zone_ready


def find_sim_info_by_name(name):
    target = clean_name(name)
    if not target:
        return None
    for sim_info in iter_sim_infos() or []:
        full_name = clean_name(sim_full_name(sim_info))
        first = clean_name(text_value(getattr(sim_info, "first_name", None), ""))
        last = clean_name(text_value(getattr(sim_info, "last_name", None), ""))
        if target in (full_name, first, (first + " " + last).strip()):
            return sim_info
    return None


def post_json(path, payload, timeout=90):
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BACKEND_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path, timeout=10):
    import urllib.request

    with urllib.request.urlopen(BACKEND_URL + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def query_json(path, params, timeout=10):
    query = urllib.parse.urlencode(params)
    suffix = path + ("?" + query if query else "")
    return get_json(suffix, timeout=timeout)


def split_chat_args(args):
    parts = [str(item) for item in args]
    if "|" in parts:
        index = parts.index("|")
        listener = " ".join(parts[:index]).strip() or "Player Sim"
        message = " ".join(parts[index + 1 :]).strip()
    else:
        listener = "Player Sim"
        message = " ".join(parts).strip()
    return listener, message


def npc_payload(name):
    sim_info = find_sim_info_by_name(name)
    if sim_info is not None:
        return sim_info_payload(sim_info)
    display_name = str(name or "").strip()
    return {"id": display_name, "name": display_name, "traits": [], "current_mood": "unknown"}


def show_chat_result(connection, speaker_name, data):
    rel = data.get("relationship") or {}
    memory = data.get("memory") or {}
    state = data.get("relationship_state") or {}
    emotion_state = data.get("emotion_state") or {}
    out(connection, "{}: {}".format(speaker_name, data.get("dialogue", "...")))
    out(
        connection,
        "emotion={} intent={} animation={}".format(
            data.get("emotion", "neutral"),
            data.get("intent", "respond"),
            data.get("animation", "friendly_chat"),
        ),
    )
    out(
        connection,
        "relationship delta: friendship {:+d}, romance {:+d}, trust {:+d}".format(
            int(rel.get("friendship_delta") or 0),
            int(rel.get("romance_delta") or 0),
            int(rel.get("trust_delta") or 0),
        ),
    )
    if state:
        out(
            connection,
            "relationship now: friendship {}, romance {}, trust {}, respect {}".format(
                state.get("friendship", 0),
                state.get("romance", 0),
                state.get("trust", 0),
                state.get("respect", 0),
            ),
        )
    if emotion_state:
        out(connection, "emotion now: {}".format(emotion_state.get("current_mood", "neutral")))
    if memory.get("summary"):
        out(connection, "memory: {}".format(memory.get("summary")))


@command("ai.help")
@command("aisims.help")
def ai_help(_connection=None):
    out(_connection, "AI Sims Agent script is loaded.")
    out(_connection, "ai.ping")
    out(_connection, "aiping")
    out(_connection, "ai.chat Bella Goth | Why have you been avoiding me?")
    out(_connection, "aichat Bella Goth | Why have you been avoiding me?")
    out(_connection, "ai.chat.async Bella Goth | Why have you been avoiding me?")
    out(_connection, "ai.profile")
    out(_connection, "ai.profile Bella Goth")
    out(_connection, "ai.memories Bella Goth")
    out(_connection, "ai.relationship Bella Goth")
    out(_connection, "ai.resolve Bella Goth")
    out(_connection, "ai.emotion")
    out(_connection, "ai.emotion Bella Goth")
    out(_connection, "ai.agents")
    out(_connection, "ai.wake")
    out(_connection, "ai.sleep")
    out(_connection, "ai.director")
    out(_connection, "aidirector")
    out(_connection, "ai.socialtunings")


@command("ai.socialtunings")
@command("aisims.socialtunings")
def ai_social_tunings(*args, _connection=None):
    query = " ".join(str(item) for item in args).strip()
    names = social_tuning_names(query)
    out(_connection, "Loaded matching social/chat tunings: {}".format(len(names)))
    for name in names:
        write_marker("social tuning: " + name)
    for name in names[:100]:
        out(_connection, name)


@command("ai.loaded")
@command("aisims.loaded")
@command("ailoaded")
def ai_loaded(_connection=None):
    write_marker("ai.loaded command ran")
    out(_connection, "AI Sims Agent script is loaded. Backend: {}".format(BACKEND_URL))


@command("ai.ping")
@command("aisims.ping")
@command("aiping")
def ai_ping(_connection=None):
    write_marker("ai.ping command ran")
    try:
        data = get_json("/health")
        out(_connection, "AI backend ok: {} at {}".format(data.get("model"), data.get("llm_base_url")))
    except Exception as exc:
        out(_connection, "AI backend error: {}".format(exc))


def chat_payload(active, target_name, message):
    player = sim_payload(active)
    target_info = find_sim_info_by_name(target_name)
    npc = sim_info_payload(target_info) if target_info is not None else npc_payload(target_name)
    return {
        "speaker": npc,
        "listener": player,
        "relationship": relationship_payload(active.sim_info, target_info),
        "location": current_location(),
        "event": {"type": "player_conversation", "source": "cheat_console"},
        "available_actions": AVAILABLE_ACTIONS,
        "message": message,
    }


@command("ai.chat")
@command("aisims.chat")
@command("aichat")
def ai_chat(*args, _connection=None):
    write_marker("ai.chat command ran")
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return

    target_name, message = split_chat_args(args)
    if not message:
        out(_connection, "Usage: ai.chat Bella Goth | Why have you been avoiding me?")
        return

    payload = chat_payload(sim, target_name, message)
    try:
        data = post_json("/chat", payload)
    except Exception as exc:
        out(_connection, "AI chat error: {}".format(exc))
        return

    show_chat_result(_connection, payload["speaker"]["name"], data)


@command("ai.chat.async")
@command("aisims.chat.async")
@command("aichatasync")
def ai_chat_async(*args, _connection=None):
    write_marker("ai.chat.async command ran")
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    target_name, message = split_chat_args(args)
    if not message:
        out(_connection, "Usage: ai.chat.async Bella Goth | Why have you been avoiding me?")
        return

    payload = chat_payload(sim, target_name, message)
    out(_connection, "AI request queued for {}.".format(payload["speaker"]["name"]))

    def worker(connection, body):
        try:
            data = post_json("/chat", body)
            show_chat_result(connection, body["speaker"]["name"], data)
        except Exception as exc:
            out(connection, "AI chat error: {}".format(exc))

    thread = threading.Thread(target=worker, args=(_connection, payload))
    thread.daemon = True
    thread.start()


@command("ai.director")
@command("aisims.director")
@command("aidirector")
def ai_director(_connection=None):
    write_marker("ai.director command ran")
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    try:
        data = post_json("/director", {"sim": sim_payload(sim)})
    except Exception as exc:
        out(_connection, "AI director error: {}".format(exc))
        return
    out(_connection, "story hook: {}".format(data.get("hook", "")))
    out(_connection, "target: {}".format(data.get("target", "")))
    out(_connection, "action: {}".format(data.get("suggested_action", "")))
    out(_connection, "tone: {}".format(data.get("tone", "neutral")))


@command("ai.agents")
@command("aisims.agents")
@command("aiagents")
def ai_agents(_connection=None):
    try:
        data = get_json("/agents/active")
    except Exception as exc:
        out(_connection, "AI agents error: {}".format(exc))
        return
    agents = data.get("active_agents") or []
    if not agents:
        out(_connection, "No active AI agents.")
        return
    for agent in agents:
        out(
            _connection,
            "{} ({}) refs={} reason={}".format(
                agent.get("name", "Unknown Sim"),
                agent.get("sim_id", ""),
                agent.get("refs", 0),
                agent.get("last_reason", ""),
            ),
        )


@command("ai.profile")
@command("aisims.profile")
@command("aiprofile")
def ai_profile(*args, _connection=None):
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    target = " ".join(str(item) for item in args).strip()
    try:
        if target:
            data = query_json("/profile", {"sim_id": target})
        else:
            data = post_json("/profile", {"sim": sim_payload(sim)})
    except Exception as exc:
        out(_connection, "AI profile error: {}".format(exc))
        return
    profile = data.get("profile") or {}
    if not profile:
        out(_connection, "No profile found.")
        return
    out(_connection, "profile: {} ({})".format(profile.get("name", ""), profile.get("id", "")))
    out(_connection, "values: {}".format(", ".join(profile.get("values") or [])))
    out(_connection, "rules: {}".format(", ".join(profile.get("behavioral_rules") or [])))


@command("ai.memories")
@command("aisims.memories")
@command("aimemories")
def ai_memories(*args, _connection=None):
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    target = " ".join(str(item) for item in args).strip()
    active = sim_payload(sim)
    params = {"sim_id": active["id"], "limit": 5}
    if target:
        params["target_id"] = target
    try:
        data = query_json("/memories", params)
    except Exception as exc:
        out(_connection, "AI memories error: {}".format(exc))
        return
    summary = data.get("summary") or {}
    if summary.get("summary"):
        out(_connection, "summary: {}".format(summary.get("summary")))
    memories = data.get("memories") or []
    if not memories:
        out(_connection, "No memories yet.")
        return
    for item in memories:
        out(_connection, "- {}".format(item.get("summary", "")))


@command("ai.relationship")
@command("aisims.relationship")
@command("airelationship")
def ai_relationship(*args, _connection=None):
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    target = " ".join(str(item) for item in args).strip()
    if not target:
        out(_connection, "Usage: ai.relationship Bella Goth")
        return
    active = sim_payload(sim)
    try:
        data = query_json("/relationship", {"sim_id": target, "target_id": active["id"]})
    except Exception as exc:
        out(_connection, "AI relationship error: {}".format(exc))
        return
    rel = data.get("relationship") or {}
    out(
        _connection,
        "relationship {} -> {}: friendship {}, romance {}, trust {}, respect {}, resentment {}".format(
            target,
            active["name"],
            rel.get("friendship", 0),
            rel.get("romance", 0),
            rel.get("trust", 0),
            rel.get("respect", 0),
            rel.get("resentment", 0),
        ),
    )


@command("ai.resolve")
@command("aisims.resolve")
@command("airesolve")
def ai_resolve(*args, _connection=None):
    target = " ".join(str(item) for item in args).strip()
    if not target:
        out(_connection, "Usage: ai.resolve Bella Goth")
        return
    sim_info = find_sim_info_by_name(target)
    if sim_info is None:
        out(_connection, "No SimInfo found for {}.".format(target))
        return
    payload = sim_info_payload(sim_info)
    out(_connection, "{} -> {}".format(payload["name"], payload["id"]))


@command("ai.emotion")
@command("aisims.emotion")
@command("aiemotion")
def ai_emotion(*args, _connection=None):
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    target = " ".join(str(item) for item in args).strip()
    active = sim_payload(sim)
    try:
        data = query_json("/emotion", {"sim_id": target or active["id"]})
    except Exception as exc:
        out(_connection, "AI emotion error: {}".format(exc))
        return
    emotion = data.get("emotion") or {}
    out(
        _connection,
        "emotion: mood {}, happiness {}, anger {}, sadness {}, stress {}, confidence {}".format(
            emotion.get("current_mood", "neutral"),
            emotion.get("happiness", 0),
            emotion.get("anger", 0),
            emotion.get("sadness", 0),
            emotion.get("stress", 0),
            emotion.get("confidence", 0),
        ),
    )


@command("ai.wake")
@command("aisims.wake")
@command("aiwake")
def ai_wake(_connection=None):
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    try:
        data = post_json("/agent/wake", {"sim": sim_payload(sim), "reason": "manual", "priority": 1})
    except Exception as exc:
        out(_connection, "AI wake error: {}".format(exc))
        return
    profile = data.get("profile") or {}
    out(_connection, "woke agent: {} ({})".format(profile.get("name", ""), profile.get("id", "")))


@command("ai.sleep")
@command("aisims.sleep")
@command("aisleep")
def ai_sleep(_connection=None):
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    active = sim_payload(sim)
    try:
        data = post_json("/agent/sleep", {"sim_id": active["id"]})
    except Exception as exc:
        out(_connection, "AI sleep error: {}".format(exc))
        return
    out(_connection, "slept agent: {}".format(data.get("slept", False)))


@command("ai.autonomous")
@command("aisims.autonomous")
@command("aiautonomous")
def ai_autonomous(_connection=None):
    sim = active_sim(_connection)
    if sim is None:
        out(_connection, "No active Sim.")
        return
    try:
        data = post_json("/autonomous", {"sim": sim_payload(sim)})
    except Exception as exc:
        out(_connection, "AI autonomous error: {}".format(exc))
        return
    out(_connection, "autonomous hook: {}".format(data.get("hook", "")))
    out(_connection, "target: {}".format(data.get("target", "")))
    out(_connection, "action: {}".format(data.get("suggested_action", "")))


try:
    write_marker("AI Sims Agent commands registered")
except Exception:
    write_marker(traceback.format_exc())
