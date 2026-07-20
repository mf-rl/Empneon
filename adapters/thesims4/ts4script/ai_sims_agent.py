import json
import os
import threading
import traceback
import urllib.parse
import uuid

import alarms
import clock
import game_services
import services
import sims4.commands
import zone
from interactions import ParticipantType
from interactions.base.super_interaction import SuperInteraction
from interactions.constraints import Anywhere, Circle
from services.persistence_service import PersistenceService
from sims.sim import Sim
from sims4.collections import FrozenAttributeDict
from sims4.localization import LocalizationHelperTuning
from sims4.tuning.tunable import AutoFactoryInit, HasTunableSingletonFactory
from sims4.utils import flexmethod
from ui.ui_dialog_generic import UiDialogTextInputOkCancel
from ui.ui_dialog_notification import UiDialogNotification
from ui.ui_text_input import UiTextInput

BACKEND_URL = "http://127.0.0.1:8765"
EMPNEON_SOCIAL_INTERACTION_ID = 16906812068311597057
AUTONOMY_INTERVAL_SIM_MINUTES = 30
NATIVE_SOCIAL_TUNINGS = {
    "friendly_chat": "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
    "apologize": "mixer_social_Apologize_targeted_friendly_lowScore",
    "flirt": "mixer_social_ComplimentAppearance_targeted_romance_alwaysOn",
}
AVAILABLE_ACTIONS = list(NATIVE_SOCIAL_TUNINGS)
_AUTONOMY_ALARM = None
_AUTONOMY_RESPONSE_ALARM = None
_AUTONOMY_CURSOR = 0
_AUTONOMY_IN_FLIGHT = False
_AUTONOMY_RESPONSES = []
_CHAT_RESPONSES = []
_AUTONOMY_RESPONSES_LOCK = threading.Lock()
_GAME_SESSION_ID = uuid.uuid4().hex
_NEW_GAME_SESSION_PENDING = False


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


write_marker("Empneon for The Sims 4 imported")


def current_save_slot_id():
    try:
        save_slot = services.get_persistence_service().get_save_slot_proto_buff()
        return str(getattr(save_slot, "slot_id", "") or "")
    except Exception:
        return ""


def prepare_game_session():
    global _GAME_SESSION_ID, _NEW_GAME_SESSION_PENDING
    if _NEW_GAME_SESSION_PENDING:
        _GAME_SESSION_ID = uuid.uuid4().hex
        _NEW_GAME_SESSION_PENDING = False


def report_game_session_start():
    prepare_game_session()

    def worker():
        try:
            post_json("/game-session/start", {}, timeout=10)
        except Exception:
            write_marker(traceback.format_exc())

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()


def report_game_session_save():
    try:
        post_json("/game-session/save", {}, timeout=10)
        write_marker("Empneon memory checkpoint saved")
    except Exception:
        write_marker(traceback.format_exc())


_ORIGINAL_SAVE_GAME_GEN = PersistenceService.save_game_gen


def _save_game_gen(self, *args, **kwargs):
    result = yield from _ORIGINAL_SAVE_GAME_GEN(self, *args, **kwargs)
    save_game_data = kwargs.get("save_game_data")
    if save_game_data is None and len(args) > 1:
        save_game_data = args[1]
    slot_id = getattr(save_game_data, "slot_id", None)
    if result == 0 and slot_id not in (None, 0, "0", ""):
        report_game_session_save()
    return result


PersistenceService.save_game_gen = _save_game_gen

_ORIGINAL_STOP_SERVICES = game_services.stop_services


def _stop_services(*args, **kwargs):
    global _NEW_GAME_SESSION_PENDING
    manager = getattr(game_services, "service_manager", None)
    if manager is not None and getattr(manager, "allow_shutdown", False):
        _NEW_GAME_SESSION_PENDING = True
    return _ORIGINAL_STOP_SERVICES(*args, **kwargs)


game_services.stop_services = _stop_services


class EmpneonSocialInteraction(SuperInteraction):
    def get_name(self, *args, **kwargs):
        return LocalizationHelperTuning.get_raw_text("Empneon Social")

    @flexmethod
    def _constraint_gen(cls, inst, sim, target, participant_type, **kwargs):
        if participant_type == ParticipantType.Actor and target is not None:
            yield Circle(target.position, 2.0, routing_surface=target.routing_surface)
        else:
            yield Anywhere()

    def _run_interaction_gen(self, timeline):
        actor = getattr(self, "sim", None)
        target = getattr(self, "target", None)
        write_marker(
            "Empneon Social selected: {} -> {}".format(
                sim_full_name(getattr(actor, "sim_info", actor)),
                sim_full_name(getattr(target, "sim_info", target)),
            )
        )
        show_empneon_message_dialog(actor, target)
        if False:
            yield None
        return True


def install_empneon_social(sim):
    try:
        affordance = services.affordance_manager().get(EMPNEON_SOCIAL_INTERACTION_ID)
        if affordance is None:
            write_marker("Empneon Social tuning not loaded")
            return False
        current = tuple(getattr(sim, "_super_affordances", ()))
        if affordance not in current:
            sim._super_affordances = current + (affordance,)
        return True
    except Exception:
        write_marker(traceback.format_exc())
        return False


_ORIGINAL_SIM_ON_ADD = Sim.on_add


def _on_sim_add(self, *args, **kwargs):
    result = _ORIGINAL_SIM_ON_ADD(self, *args, **kwargs)
    install_empneon_social(self)
    return result


Sim.on_add = _on_sim_add


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
            name = str(display_name(sim_info))
        else:
            name = str(display_name or short_trait_name(mood))
        name = name.strip().casefold()
        if name.startswith("mood_"):
            name = name[5:]
        return name or "unknown"
    except Exception:
        return "unknown"


def _tracker_items(tracker):
    for attr in ("get_all_commodities", "statistics", "values"):
        try:
            source = getattr(tracker, attr, None)
            if source is None:
                continue
            items = source() if callable(source) else source
            if isinstance(items, dict):
                items = items.values()
            return list(items or [])[:20]
        except Exception:
            pass
    return []


def _stat_values(tracker):
    result = {}
    for stat in _tracker_items(tracker):
        try:
            name = short_trait_name(getattr(stat, "stat_type", stat))
            getter = getattr(stat, "get_value", None)
            value = getter() if callable(getter) else getattr(stat, "value", None)
            if name and isinstance(value, (int, float)):
                result[name] = int(round(max(0, min(100, value))))
        except Exception:
            pass
    return result


def sim_needs(sim_info):
    tracker = getattr(sim_info, "commodity_tracker", None)
    if tracker is None:
        try:
            tracker = getattr(sim_info.get_sim_instance(), "commodity_tracker", None)
        except Exception:
            pass
    needs = {}
    allowed = ("bladder", "energy", "fun", "hunger", "hygiene", "social")
    for raw_name, value in _stat_values(tracker).items():
        name = raw_name.strip().casefold()
        if name.startswith("motive_"):
            name = name[7:]
        if name in allowed:
            needs[name] = value
    return needs


def sim_age(sim_info):
    value = getattr(sim_info, "age", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(getattr(value, "value", None))
        except (TypeError, ValueError):
            return None


def sim_moodlets(sim_info):
    component = getattr(sim_info, "buff_component", None)
    if component is None:
        try:
            component = getattr(sim_info.get_sim_instance(), "buff_component", None)
        except Exception:
            pass
    try:
        source = getattr(component, "get_all_buffs", None)
        buffs = source() if callable(source) else source or []
        return [
            name
            for name in (
                short_trait_name(getattr(buff, "buff_type", buff))
                for buff in list(buffs)[:20]
            )
            if name
        ]
    except Exception:
        return []


def sim_aspiration(sim_info):
    tracker = getattr(sim_info, "aspiration_tracker", None)
    for source in (tracker, sim_info):
        for attr in ("active_aspiration", "primary_aspiration", "_active_aspiration"):
            name = short_trait_name(getattr(source, attr, None))
            if name:
                return name
        for method_name in ("get_primary_aspiration", "get_active_aspiration"):
            try:
                name = short_trait_name(getattr(source, method_name)())
                if name:
                    return name
            except Exception:
                pass
    return "unknown"


def sim_career(sim_info):
    tracker = getattr(sim_info, "career_tracker", None)
    try:
        careers = getattr(tracker, "careers", {}) or {}
        values = careers.values() if isinstance(careers, dict) else careers
        for career in list(values)[:20]:
            name = short_trait_name(
                getattr(career, "current_track_tuning", None) or career
            )
            if name:
                return name
    except Exception:
        pass
    return "unknown"


def sim_skills(sim_info):
    tracker = getattr(sim_info, "skill_tracker", None) or getattr(
        sim_info, "statistic_skill_tracker", None
    )
    return _stat_values(tracker)


def sim_household(sim_info):
    household = getattr(sim_info, "household", None)
    if household is None:
        return {}
    household_id = getattr(household, "id", None) or getattr(
        sim_info, "household_id", None
    )
    name = text_value(getattr(household, "name", None), "")
    return {"id": str(household_id or ""), "name": name}


def sim_info_payload(sim_info):
    return {
        "id": str(getattr(sim_info, "sim_id", sim_full_name(sim_info))),
        "name": sim_full_name(sim_info),
        "age": sim_age(sim_info),
        "traits": sim_traits(sim_info),
        "current_mood": sim_mood(sim_info),
        "needs": sim_needs(sim_info),
        "moodlets": sim_moodlets(sim_info),
        "aspiration": sim_aspiration(sim_info),
        "career": sim_career(sim_info),
        "skills": sim_skills(sim_info),
        "household": sim_household(sim_info),
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
    result = {"friendship": 0, "romance": 0, "trust": 50, "resentment": 0}
    if target_info is None:
        return result
    tracker = getattr(source_info, "relationship_tracker", None)
    target_id = getattr(target_info, "sim_id", None)
    found_track = False
    for key, tuning_name in (
        ("friendship", "LTR_Friendship_Main"),
        ("romance", "LTR_Romance_Main"),
    ):
        track = None
        for resource_name in ("STATISTIC", "RELATIONSHIP_TRACK"):
            try:
                resource_type = getattr(sims4.resources.Types, resource_name, None)
                if resource_type is None:
                    continue
                manager = services.get_instance_manager(resource_type)
                track = next(
                    (
                        tuning
                        for tuning in manager.types.values()
                        if getattr(tuning, "__name__", "") == tuning_name
                    ),
                    None,
                )
                if track is not None:
                    break
            except Exception:
                pass
        if track is None:
            continue
        track_read = False
        for method_name in ("get_relationship_score", "get_relationship_score_by_sim_id"):
            method = getattr(tracker, method_name, None)
            if not callable(method):
                continue
            for target in (target_info, target_id):
                try:
                    raw_score = float(method(target, track))
                    low = -100 if key == "friendship" else 0
                    result[key] = int(max(low, min(100, round(raw_score))))
                    found_track = True
                    track_read = True
                    break
                except Exception:
                    pass
            if track_read:
                break
    if found_track:
        return result
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


def nearby_sim_payloads(*excluded):
    excluded_ids = {str(value) for value in excluded}
    return [
        sim_info_payload(info)
        for info in instanced_npc_infos()[:20]
        if str(getattr(info, "sim_id", "")) not in excluded_ids
    ]


def autonomous_tick(_alarm_handle):
    global _AUTONOMY_CURSOR, _AUTONOMY_IN_FLIGHT
    if _AUTONOMY_IN_FLIGHT:
        return
    candidates = instanced_npc_infos()
    if len(candidates) < 2:
        return
    selected_interaction = None
    speaker = None
    listener = None
    skip_reason = "no scored NPC interaction"
    for offset in range(len(candidates)):
        speaker = candidates[(_AUTONOMY_CURSOR + offset) % len(candidates)]
        actor = speaker.get_sim_instance()
        request = actor.autonomy_component._create_autonomy_request()
        selected = services.autonomy_service().find_best_action(request)
        target = getattr(selected, "target", None)
        target_info = getattr(target, "sim_info", None)
        if target_info is not None and target is not actor and not target.is_selectable:
            selected_interaction = selected
            listener = target_info
            _AUTONOMY_CURSOR = (_AUTONOMY_CURSOR + offset + 1) % len(candidates)
            break
        if target_info is not None:
            skip_reason = "selected non-NPC target " + str(
                getattr(target_info, "sim_id", "unknown")
            )
    if selected_interaction is None:
        write_marker("autonomy skipped: " + skip_reason)
        return
    payload = {
        "speaker": sim_info_payload(speaker),
        "listener": sim_info_payload(listener),
        "relationship": relationship_payload(speaker, listener),
        "location": current_location(),
        "nearby_sims": nearby_sim_payloads(speaker.sim_id, listener.sim_id),
        "event": {"type": "autonomous_social", "source": "sim_alarm"},
        "available_actions": AVAILABLE_ACTIONS,
    }
    _AUTONOMY_IN_FLIGHT = True

    def worker():
        try:
            data = post_json("/autonomous", payload)
            with _AUTONOMY_RESPONSES_LOCK:
                _AUTONOMY_RESPONSES.append((payload, data, selected_interaction))
        except Exception:
            global _AUTONOMY_IN_FLIGHT
            _AUTONOMY_IN_FLIGHT = False
            write_marker(traceback.format_exc())

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()


def process_autonomy_responses(_alarm_handle):
    with _AUTONOMY_RESPONSES_LOCK:
        chat_item = _CHAT_RESPONSES.pop(0) if _CHAT_RESPONSES else None
        item = _AUTONOMY_RESPONSES.pop(0) if _AUTONOMY_RESPONSES else None
    if chat_item is not None:
        try:
            show_empneon_chat_result(*chat_item)
        except Exception:
            write_marker(traceback.format_exc())
    if item is None:
        return
    payload, data, selected_interaction = item
    execute_sims_action(payload, data, selected_interaction)


def execute_sims_action(payload, data, interaction):
    decision_id = str(data.get("decision_id") or "")
    action = str(data.get("suggested_action") or data.get("animation") or "")
    speaker_id = str(payload["speaker"]["id"])
    listener_id = str(payload["listener"]["id"])
    try:
        actor_info = find_sim_info_by_id(listener_id if interaction is None else speaker_id)
        target_info = find_sim_info_by_id(speaker_id if interaction is None else listener_id)
        actor = actor_info.get_sim_instance() if actor_info is not None else None
        target = target_info.get_sim_instance() if target_info is not None else None
        if actor is None or target is None:
            raise RuntimeError("actor or target left the active zone")
        affordance = find_action_affordance(action)
        if affordance is None:
            raise RuntimeError("no native social mapped for {}".format(action))
        from interactions.aop import AffordanceObjectPair

        from interactions.context import InteractionContext
        from interactions.priority import Priority
        import sims4.resources

        bit_manager = services.get_instance_manager(sims4.resources.Types.RELATIONSHIP_BIT)
        has_met = next(
            (
                tuning
                for tuning in bit_manager.types.values()
                if getattr(tuning, "__name__", "") == "has_met"
            ),
            None,
        )
        tracker = getattr(actor_info, "relationship_tracker", None)
        if has_met is not None and tracker is not None and not tracker.has_bit(target_info.sim_id, has_met):
            tracker.add_relationship_bit(target_info.sim_id, has_met)
            write_marker("established has_met: {} -> {}".format(listener_id, speaker_id))

        context = InteractionContext(
            actor,
            InteractionContext.SOURCE_SCRIPT_WITH_USER_INTENT,
            Priority.High,
        )
        mapped_aop = None
        mapped_interaction = None
        failures = []
        candidates = tuple(target.potential_interactions(context))
        for candidate in candidates:
            candidate_name = getattr(candidate.affordance, "__name__", "unknown")
            try:
                available = getattr(candidate.affordance, "all_affordances_gen", None)
                if not callable(available) or affordance not in tuple(available(context=context)):
                    continue
                proposed = AffordanceObjectPair(
                    affordance,
                    target,
                    candidate.affordance,
                    None,
                    push_super_on_prepare=True,
                )
                test_result = proposed.test(context)
                factory_result = proposed.interaction_factory(context) if test_result else None
                if factory_result:
                    mapped_aop = proposed
                    mapped_interaction = factory_result.interaction
                    break
                failures.append("{}={}".format(candidate_name, test_result))
            except Exception as exc:
                failures.append("{}={!r}".format(candidate_name, exc))

        if mapped_aop is None:
            details = "; ".join(failures[:8])
            if not details:
                details = (
                    "no compatible social super-interaction offers {}"
                ).format(action)
            raise RuntimeError(
                "native social failed game selection for {}: {}".format(
                    action, details
                )
            )
        if mapped_interaction is None:
            test_result = mapped_aop.test(context)
            if not test_result:
                raise RuntimeError("native social failed game tests: {}".format(test_result))
            factory_result = mapped_aop.interaction_factory(context)
            if not factory_result:
                raise RuntimeError("native social could not be created: {}".format(factory_result))
            mapped_interaction = factory_result.interaction
        callback = getattr(mapped_interaction, "register_on_finishing_callback", None)
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
        if not AffordanceObjectPair.execute_interaction(mapped_interaction):
            raise RuntimeError("game rejected native interaction")
        write_marker(
            "queued {} -> {}: {} ({})".format(
                payload["speaker"]["name"],
                payload["listener"]["name"],
                action,
                getattr(affordance, "__name__", "unknown"),
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
            write_marker(
                "confirmed {}: {} ({}){}".format(
                    decision_id,
                    action,
                    status,
                    " reason=" + str(reason) if reason else "",
                )
            )
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
    tuning_name = NATIVE_SOCIAL_TUNINGS.get(action)
    return next(
        (
            tuning
            for tuning in loaded_interaction_tunings()
            if getattr(tuning, "__name__", "") == tuning_name
        ),
        None,
    )


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
    report_game_session_start()
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

    payload = dict(payload)
    payload["_empneon_session_id"] = _GAME_SESSION_ID
    payload["_empneon_save_slot_id"] = current_save_slot_id()
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


def raw_text(text):
    return lambda **_: LocalizationHelperTuning.get_raw_text(str(text))


def show_empneon_notification(owner, title, text):
    notification = UiDialogNotification.TunableFactory().default(
        owner,
        title=raw_text(title),
        text=raw_text(text),
    )
    notification.show_dialog()


class EmpneonTextInputLength(HasTunableSingletonFactory, AutoFactoryInit):
    def build_msg(self, dialog, msg, *additional_tokens):
        msg.max_length = 280
        msg.min_length = 1
        msg.input_too_short_tooltip = LocalizationHelperTuning.get_raw_text(
            "Enter at least one character."
        )


def show_empneon_message_dialog(actor, target, transcript=""):
    if actor is None or target is None:
        write_marker("Empneon Social canceled: actor or target unavailable")
        return
    target_name = sim_full_name(getattr(target, "sim_info", target))
    message_input = UiTextInput(sort_order=0, restricted_characters=None)
    message_input.default_text = raw_text("Type a message...")
    message_input.title = None
    message_input.initial_value = None
    message_input.check_profanity = False
    message_input.height = None
    message_input.length_restriction = EmpneonTextInputLength()
    # The game checks text-input names with hasattr(), so this must support
    # attribute lookup as well as mapping iteration.
    inputs = FrozenAttributeDict({"message": message_input})
    dialog = UiDialogTextInputOkCancel.TunableFactory().default(
        actor,
        title=raw_text("{} says:".format(target_name)),
        text=raw_text(
            transcript
            or "What should {} say to {}?".format(sim_full_name(actor.sim_info), target_name)
        ),
        text_inputs=inputs,
    )

    def on_response(response):
        if not getattr(response, "accepted", False):
            write_marker("Empneon Social input canceled")
            return
        responses = getattr(response, "text_input_responses", {}) or {}
        value = responses.get("message")
        if not value:
            value = next((item for item in responses.values() if item), "")
        message = str(getattr(value, "text", value) or "").strip()
        write_marker(
            "Empneon Social input keys={} length={}".format(
                tuple(str(key) for key in responses),
                len(message),
            )
        )
        if not message:
            show_empneon_notification(actor, "Empneon Social", "Enter a message before sending.")
            return
        submit_empneon_chat(actor, target, message, transcript)

    dialog.add_listener(on_response)
    dialog.show_dialog()


def submit_empneon_chat(actor, target, message, transcript=""):
    payload = chat_payload_for_target(
        actor,
        getattr(target, "sim_info", None),
        message,
        "pie_menu",
    )
    speaker_name = sim_full_name(getattr(actor, "sim_info", actor))
    transcript = "{}\n\n{}: {}".format(transcript, speaker_name, message).strip()
    show_empneon_notification(actor, "Empneon Social", "Thinking...")

    def worker():
        try:
            data = post_json("/chat", payload)
            data["_empneon_payload"] = payload
            result = (actor, target, data, None, transcript)
        except Exception as exc:
            result = (actor, target, None, str(exc), transcript)
        with _AUTONOMY_RESPONSES_LOCK:
            _CHAT_RESPONSES.append(result)

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()


def show_empneon_chat_result(actor, target, data, error, transcript=""):
    target_name = sim_full_name(getattr(target, "sim_info", target))
    if error:
        show_empneon_notification(actor, "Empneon error", error)
        write_marker("Empneon Social failed: " + error)
        return
    payload = data.pop("_empneon_payload", None)
    if payload is not None and data.get("decision_id"):
        execute_sims_action(payload, data, None)
    relationship = data.get("relationship") or {}
    details = "Emotion: {} | Intent: {} | Suggested action: {}".format(
        data.get("emotion", "neutral"),
        data.get("intent", "respond"),
        data.get("animation", "friendly_chat"),
    )
    deltas = [
        "{} {:+d}".format(label, int(relationship.get(key) or 0))
        for label, key in (
            ("Friendship", "friendship_delta"),
            ("Romance", "romance_delta"),
            ("Trust", "trust_delta"),
        )
        if int(relationship.get(key) or 0)
    ]
    if deltas:
        details += "\nEmpneon state: " + ", ".join(deltas)
    dialogue = str(data.get("dialogue") or "...")
    transcript = "{}\n\n{}: {}\n\n{}".format(
        transcript,
        target_name,
        dialogue,
        details,
    ).strip()
    show_empneon_message_dialog(actor, target, transcript)
    write_marker("Empneon Social response from {}: {}".format(target_name, dialogue))


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
    out(_connection, "Empneon for The Sims 4 is loaded.")
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
    out(_connection, "Empneon for The Sims 4 is loaded. Backend: {}".format(BACKEND_URL))


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


def chat_payload_for_target(active, target_info, message, source):
    player = sim_payload(active)
    npc = sim_info_payload(target_info)
    return {
        "speaker": npc,
        "listener": player,
        "relationship": relationship_payload(target_info, active.sim_info),
        "location": current_location(),
        "nearby_sims": nearby_sim_payloads(npc["id"], player["id"]),
        "event": {"type": "player_conversation", "source": source},
        "available_actions": AVAILABLE_ACTIONS,
        "message": message,
    }


def chat_payload(active, target_name, message):
    target_info = find_sim_info_by_name(target_name)
    if target_info is not None:
        return chat_payload_for_target(active, target_info, message, "cheat_console")
    player = sim_payload(active)
    return {
        "speaker": npc_payload(target_name),
        "listener": player,
        "relationship": relationship_payload(active.sim_info, None),
        "location": current_location(),
        "nearby_sims": nearby_sim_payloads(player["id"]),
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


def active_diagnostic(path, connection):
    sim = active_sim(connection)
    if sim is None:
        out(connection, "No active Sim.")
        return None
    try:
        return query_json(path, {"sim_id": sim_payload(sim)["id"]})
    except Exception as exc:
        out(connection, "Empneon diagnostic error: {}".format(exc))
        return None


@command("empneon.status")
def empneon_status(_connection=None):
    data = active_diagnostic("/diagnostics/sim", _connection)
    if data is None:
        return
    agent = data.get("agent") or {}
    out(
        _connection,
        "Empneon: {} | goals={} beliefs={} memories={}".format(
            agent.get("name", "Unknown Sim"),
            len(data.get("goals") or []),
            len(data.get("beliefs") or []),
            len(data.get("accessible_memories") or []),
        ),
    )


@command("empneon.timeline")
def empneon_timeline(_connection=None):
    data = active_diagnostic("/diagnostics/timeline", _connection)
    if data is None:
        return
    entries = data.get("entries") or []
    out(_connection, "Timeline entries: {}".format(len(entries)))
    for entry in entries[:5]:
        out(_connection, "- {} {}".format(entry.get("type", ""), entry.get("id", "")))


@command("empneon.beliefs")
def empneon_beliefs(_connection=None):
    data = active_diagnostic("/diagnostics/sim", _connection)
    if data is None:
        return
    beliefs = data.get("beliefs") or []
    out(_connection, "Beliefs: {}".format(len(beliefs)))
    for belief in beliefs[:5]:
        out(_connection, "- {}".format(belief.get("statement", "")))


@command("empneon.goals")
def empneon_goals(_connection=None):
    data = active_diagnostic("/diagnostics/sim", _connection)
    if data is None:
        return
    goals = data.get("goals") or []
    out(_connection, "Goals: {}".format(len(goals)))
    for goal in goals[:5]:
        out(
            _connection,
            "- [{}] {}".format(goal.get("status", ""), goal.get("description", "")),
        )


@command("empneon.usage")
def empneon_usage(_connection=None):
    data = active_diagnostic("/diagnostics/usage", _connection)
    if data is None:
        return
    actual = data.get("actual") or {}
    out(
        _connection,
        "Usage: requests={} CLOD={} prompt={} completion={} latency={}ms".format(
            data.get("requests", 0),
            data.get("by_clod") or {},
            actual.get("prompt_tokens", 0),
            actual.get("completion_tokens", 0),
            actual.get("latency_ms", 0),
        ),
    )


try:
    write_marker("Empneon for The Sims 4 commands registered")
except Exception:
    write_marker(traceback.format_exc())
