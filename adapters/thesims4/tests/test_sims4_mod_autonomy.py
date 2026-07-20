import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import build_mod


def test_empneon_diagnostic_commands_are_registered() -> None:
    source = (Path(__file__).parents[1] / "ts4script" / "ai_sims_agent.py").read_text(
        encoding="utf-8"
    )
    for command in (
        "empneon.status",
        "empneon.timeline",
        "empneon.beliefs",
        "empneon.goals",
        "empneon.usage",
    ):
        assert f'@command("{command}")' in source


def test_build_and_installer_use_empneon_artifact_names() -> None:
    root = Path(__file__).parents[1]
    installer = (root / "install_mod.ps1").read_text(encoding="utf-8")

    assert build_mod.TARGET.name == "Empneon_TheSims4.ts4script"
    assert build_mod.TUNING_TARGET.name == "Empneon_TheSims4.package"
    assert '"Empneon_TheSims4.ts4script"' in installer
    assert '"Empneon_TheSims4.package"' in installer
    assert '"AI_Sims_Agent.ts4script"' in installer
    assert '"AI_Sims_Agent.package"' in installer
    assert "if (-not ((Test-Path $scriptSource) -and (Test-Path $tuningSource)))" in installer


def test_tuning_package_uses_interaction_resource_type() -> None:
    written = []
    target = SimpleNamespace(write_bytes=written.append)
    build_mod.build_tuning_package(build_mod.TUNING_SOURCE, target)
    package = written[0]
    count, index_offset, index_size = struct.unpack_from("<III", package, 36)
    index_flags, resource_type = struct.unpack_from("<II", package, index_offset)

    assert package[:4] == b"DBPF"
    assert (count, index_size, index_flags) == (1, 36, 0)
    assert resource_type == 0xE882D22F


def test_alarm_submits_one_npc_pair_without_overlap(monkeypatch) -> None:
    project = Path(__file__).parents[1]
    monkeypatch.setenv("HOME", str(project / "tests"))
    monkeypatch.setenv("USERPROFILE", str(project / "tests"))
    alarms = ModuleType("alarms")
    alarms.cancel_alarm = lambda _handle: None
    alarms.add_alarm = lambda *_args, **_kwargs: object()
    clock = ModuleType("clock")
    clock.interval_in_sim_minutes = lambda minutes: minutes
    game_services = ModuleType("game_services")
    game_services.service_manager = SimpleNamespace(allow_shutdown=True)
    game_services.stop_services = lambda: None
    services = ModuleType("services")
    persistence_service = ModuleType("services.persistence_service")

    class FakePersistenceService:
        def get_save_slot_proto_buff(self):
            return SimpleNamespace(slot_id="slot-1")

        def save_game_gen(self, _timeline=None, _save_game_data=None, result=0):
            yield "saving"
            return result

    persistence = FakePersistenceService()
    persistence_service.PersistenceService = FakePersistenceService
    services.get_persistence_service = lambda: persistence

    interactions = ModuleType("interactions")
    interactions.ParticipantType = SimpleNamespace(Actor="actor")
    interactions_base = ModuleType("interactions.base")
    super_interaction = ModuleType("interactions.base.super_interaction")
    super_interaction.SuperInteraction = type("SuperInteraction", (), {})
    constraints = ModuleType("interactions.constraints")
    constraints.Anywhere = lambda: SimpleNamespace(kind="anywhere")
    constraints.Circle = lambda center, radius, routing_surface=None: SimpleNamespace(
        kind="circle", center=center, radius=radius, routing_surface=routing_surface
    )
    aop_module = ModuleType("interactions.aop")
    context_module = ModuleType("interactions.context")

    class FakeInteractionContext:
        SOURCE_SCRIPT_WITH_USER_INTENT = "script_with_user_intent"

        def __init__(self, sim, source, priority):
            self.sim = sim
            self.source = source
            self.priority = priority

    context_module.InteractionContext = FakeInteractionContext
    priority_module = ModuleType("interactions.priority")
    priority_module.Priority = SimpleNamespace(High="high")
    executed = []
    mapped_aops = []
    failed_factories = set()


    class FakeMappedInteraction:
        def __init__(self, affordance):
            self.affordance = affordance
            self.finishing_type = ""
            self.finishing_callback = None

        def register_on_finishing_callback(self, callback):
            self.finishing_callback = callback

    class FakeAffordanceObjectPair:
        def __init__(self, affordance, target, super_affordance, super_interaction, **kwargs):
            self.affordance = affordance
            self.target = target
            self.super_affordance = super_affordance
            self.super_interaction = super_interaction
            self.__dict__.update(kwargs)
            mapped_aops.append(self)

        def test(self, _context):
            return True

        def interaction_factory(self, _context):
            if self.super_affordance in failed_factories:
                raise TypeError("get_name() got multiple values for argument 'target'")
            return SimpleNamespace(interaction=FakeMappedInteraction(self.affordance))

        @staticmethod
        def execute_interaction(interaction):
            executed.append(interaction)
            return True

    aop_module.AffordanceObjectPair = FakeAffordanceObjectPair
    commands = ModuleType("sims4.commands")
    commands.CommandType = SimpleNamespace(Live="live")
    commands.Command = lambda *_args, **_kwargs: lambda function: function
    commands.CheatOutput = lambda _connection: lambda _text: None
    sims4 = ModuleType("sims4")
    sims4.commands = commands
    collections = ModuleType("sims4.collections")

    class FrozenAttributeDict(dict):
        __getattr__ = dict.__getitem__

    collections.FrozenAttributeDict = FrozenAttributeDict
    resources = ModuleType("sims4.resources")
    resources.Types = SimpleNamespace(
        INTERACTION="interaction", RELATIONSHIP_BIT="relationship_bit", STATISTIC="statistic"
    )
    resources.get_resource_key = lambda name, resource_type: (name, resource_type)
    sims4.resources = resources
    localization = ModuleType("sims4.localization")
    localization.LocalizationHelperTuning = SimpleNamespace(get_raw_text=lambda text: text)
    sims = ModuleType("sims")
    sim_module = ModuleType("sims.sim")
    sim_module.Sim = type("Sim", (), {"on_add": lambda self: "added"})
    ui = ModuleType("ui")
    ui_dialog_generic = ModuleType("ui.ui_dialog_generic")
    ui_dialog_notification = ModuleType("ui.ui_dialog_notification")
    ui_text_input = ModuleType("ui.ui_text_input")
    tunable = ModuleType("sims4.tuning.tunable")
    tunable.AutoFactoryInit = type("AutoFactoryInit", (), {})
    tunable.HasTunableSingletonFactory = type("HasTunableSingletonFactory", (), {})
    utils = ModuleType("sims4.utils")

    class flexmethod:
        def __init__(self, function):
            self.function = function

        def __get__(self, instance, owner):
            return lambda *args, **kwargs: self.function(
                owner, instance, *args, **kwargs
            )

    utils.flexmethod = flexmethod

    class UiTextInput:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def build_msg(self, *args):
            return None

    ui_text_input.UiTextInput = UiTextInput
    dialogs = []
    notifications = []

    class FakeDialog:
        def __init__(self, owner, kwargs):
            self.owner = owner
            self.kwargs = kwargs
            self.accepted = False
            self.text_input_responses = {}
            self.listener = None

        def add_listener(self, listener):
            self.listener = listener

        def show_dialog(self, **kwargs):
            self.show_kwargs = kwargs

    def dialog_default(owner, **kwargs):
        dialog = FakeDialog(owner, kwargs)
        dialogs.append(dialog)
        return dialog

    def notification_default(owner, **kwargs):
        notification = FakeDialog(owner, kwargs)
        notifications.append(notification)
        return notification

    ui_dialog_generic.UiDialogTextInputOkCancel = SimpleNamespace(
        TunableFactory=lambda: SimpleNamespace(default=dialog_default)
    )
    ui_dialog_notification.UiDialogNotification = SimpleNamespace(
        TunableFactory=lambda: SimpleNamespace(default=notification_default)
    )
    zone = ModuleType("zone")
    zone.Zone = type("Zone", (), {"on_loading_screen_animation_finished": lambda self: None})
    for name, module in {
        "alarms": alarms,
        "clock": clock,
        "game_services": game_services,
        "interactions": interactions,
        "interactions.base": interactions_base,
        "interactions.base.super_interaction": super_interaction,
        "interactions.constraints": constraints,
        "interactions.aop": aop_module,
        "interactions.context": context_module,
        "interactions.priority": priority_module,
        "services": services,
        "services.persistence_service": persistence_service,
        "sims": sims,
        "sims.sim": sim_module,
        "sims4": sims4,
        "sims4.collections": collections,
        "sims4.commands": commands,
        "sims4.localization": localization,
        "sims4.resources": resources,
        "sims4.tuning.tunable": tunable,
        "sims4.utils": utils,
        "ui": ui,
        "ui.ui_dialog_generic": ui_dialog_generic,
        "ui.ui_dialog_notification": ui_dialog_notification,
        "ui.ui_text_input": ui_text_input,
        "zone": zone,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    path = project / "ts4script" / "ai_sims_agent.py"
    spec = importlib.util.spec_from_file_location("test_ai_sims_agent", path)
    assert spec and spec.loader
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)

    for probe in (
        "sim_needs",
        "sim_moodlets",
        "sim_aspiration",
        "sim_career",
        "sim_skills",
        "sim_household",
    ):
        assert hasattr(agent, probe)
    hunger = SimpleNamespace(
        stat_type=type("motive_Hunger", (), {}),
        get_value=lambda: 18,
    )
    internal_stat = SimpleNamespace(
        stat_type=type("commodity_burnout_mentaltracker", (), {}),
        get_value=lambda: 5,
    )
    cooking = SimpleNamespace(
        stat_type=type("Cooking", (), {}),
        get_value=lambda: 7,
    )
    rich_info = SimpleNamespace(
        sim_id="bella",
        full_name="Bella",
        age=42,
        get_mood=lambda: type("mood_uncomfortable", (), {}),
        trait_tracker=None,
        commodity_tracker=SimpleNamespace(
            get_all_commodities=lambda: [hunger, internal_stat]
        ),
        buff_component=SimpleNamespace(
            get_all_buffs=lambda: [SimpleNamespace(buff_type=type("Uncomfortable", (), {}))]
        ),
        aspiration_tracker=SimpleNamespace(
            active_aspiration=type("MasterChef", (), {})
        ),
        career_tracker=SimpleNamespace(
            careers={1: SimpleNamespace(current_track_tuning=type("Painter", (), {}))}
        ),
        skill_tracker=SimpleNamespace(statistics=[cooking]),
        household=SimpleNamespace(id=42, name="Goth Household"),
    )
    rich_payload = agent.sim_info_payload(rich_info)
    assert rich_payload["age"] == 42
    assert rich_payload["current_mood"] == "uncomfortable"
    assert rich_payload["needs"] == {"hunger": 18}
    assert rich_payload["moodlets"] == ["Uncomfortable"]
    assert rich_payload["aspiration"] == "MasterChef"
    assert rich_payload["career"] == "Painter"
    assert rich_payload["skills"] == {"Cooking": 7}
    assert rich_payload["household"] == {"id": "42", "name": "Goth Household"}

    method_info = SimpleNamespace(
        aspiration_tracker=SimpleNamespace(
            get_primary_aspiration=lambda: type("Bodybuilder", (), {})
        )
    )
    assert agent.sim_aspiration(method_info) == "Bodybuilder"

    friendship_track = type("LTR_Friendship_Main", (), {})
    romance_track = type("LTR_Romance_Main", (), {})
    track_manager = SimpleNamespace(types={1: friendship_track, 2: romance_track})
    agent.services.get_instance_manager = lambda _resource_type: track_manager
    scores = {friendship_track: -20, romance_track: 15}
    source_info = SimpleNamespace(
        relationship_tracker=SimpleNamespace(
            get_relationship_score=lambda _target, track=None: scores[track]
        )
    )
    target_info = SimpleNamespace(sim_id="mortimer")
    relationship = agent.relationship_payload(source_info, target_info)
    assert relationship["friendship"] == -20
    assert relationship["romance"] == 15

    relationship_queries = []
    with monkeypatch.context() as command_patch:
        command_patch.setattr(
            agent,
            "active_sim",
            lambda _connection: SimpleNamespace(sim_info=rich_info),
        )
        command_patch.setattr(
            agent,
            "find_sim_info_by_name",
            lambda name: SimpleNamespace(sim_id="cam-id", full_name="Cam Sadya")
            if name == "Cam Sadya"
            else None,
        )
        command_patch.setattr(
            agent,
            "query_json",
            lambda path, query: relationship_queries.append((path, query))
            or {"relationship": {}},
        )
        agent.ai_relationship("Cam", "Sadya")
    assert relationship_queries == [
        ("/relationship", {"sim_id": "cam-id", "target_id": "bella"})
    ]

    save_reports = []
    monkeypatch.setattr(
        agent,
        "post_json",
        lambda path, payload, timeout=90: save_reports.append((path, payload, timeout)),
    )
    save = persistence.save_game_gen(None, SimpleNamespace(slot_id=2))
    assert next(save) == "saving"
    try:
        next(save)
    except StopIteration as completed:
        assert completed.value == 0
    else:
        raise AssertionError("save callback ran before the game save completed")
    assert save_reports == [("/game-session/save", {}, 10)]

    for slot_id, result in ((0, 0), (2, 2)):
        save = persistence.save_game_gen(None, SimpleNamespace(slot_id=slot_id), result)
        next(save)
        try:
            next(save)
        except StopIteration:
            pass
    assert save_reports == [("/game-session/save", {}, 10)]

    session_id = agent._GAME_SESSION_ID
    game_services.service_manager.allow_shutdown = False
    game_services.stop_services()
    agent.prepare_game_session()
    assert agent._GAME_SESSION_ID == session_id

    game_services.service_manager.allow_shutdown = True
    game_services.stop_services()
    assert agent._GAME_SESSION_ID == session_id
    agent.prepare_game_session()
    assert agent._GAME_SESSION_ID != session_id

    pie_affordance = type("EmpneonSocialTuning", (), {})
    services.affordance_manager = lambda: SimpleNamespace(
        get=lambda tuning_id: pie_affordance
        if tuning_id == agent.EMPNEON_SOCIAL_INTERACTION_ID
        else None
    )
    pie_sim = sim_module.Sim()
    pie_sim._super_affordances = ()
    assert agent.install_empneon_social(pie_sim) is True
    assert agent.install_empneon_social(pie_sim) is True
    assert pie_sim._super_affordances == (pie_affordance,)
    assert pie_sim.on_add() == "added"
    assert pie_sim._super_affordances == (pie_affordance,)
    selected = []
    monkeypatch.setattr(agent, "write_marker", selected.append)
    submitted = []
    monkeypatch.setattr(
        agent,
        "submit_empneon_chat",
        lambda actor, target, message, transcript="": submitted.append(
            (actor, target, message, transcript)
        ),
    )
    pie_interaction = agent.EmpneonSocialInteraction()
    pie_interaction.sim = SimpleNamespace(sim_info=SimpleNamespace(full_name="Alice"))
    pie_interaction.target = SimpleNamespace(sim_info=SimpleNamespace(full_name="Bob"))
    try:
        next(pie_interaction._run_interaction_gen(None))
    except StopIteration as finished:
        assert finished.value is True
    assert selected == ["Empneon Social selected: Alice -> Bob"]
    assert agent.EmpneonSocialInteraction.get_name(None, None) == "Empneon Social"
    assert pie_interaction.get_name() == "Empneon Social"
    route_target = SimpleNamespace(position="position", routing_surface="surface")
    route_constraint = next(
        agent.EmpneonSocialInteraction._constraint_gen(
            pie_interaction.sim, route_target, "actor"
        )
    )
    assert (route_constraint.kind, route_constraint.center, route_constraint.radius) == (
        "circle",
        "position",
        2.0,
    )
    dialog = dialogs[-1]
    assert hasattr(dialog.kwargs["text_inputs"], "message")
    text_input = dialog.kwargs["text_inputs"]["message"]
    assert callable(text_input.build_msg)
    assert text_input.check_profanity is False
    assert text_input.height is None
    assert isinstance(
        text_input.length_restriction,
        agent.EmpneonTextInputLength,
    )
    assert dialog.show_kwargs == {}
    dialog.accepted = True
    dialog.text_input_responses = {"message": "  Remember our promise?  "}
    dialog.listener(dialog)
    assert submitted == [
        (pie_interaction.sim, pie_interaction.target, "Remember our promise?", "")
    ]

    notification_count = len(notifications)
    agent.show_empneon_chat_result(
        pie_interaction.sim,
        pie_interaction.target,
        {
            "dialogue": "I remember.",
            "emotion": "warm",
            "intent": "reassure",
            "animation": "friendly_chat",
            "relationship": {"trust_delta": 2},
        },
        None,
        "Alice: Remember our promise?",
    )
    chat_dialog = dialogs[-1]
    assert chat_dialog.kwargs["title"]() == "Bob says:"
    assert "Alice: Remember our promise?" in chat_dialog.kwargs["text"]()
    assert "Bob: I remember." in chat_dialog.kwargs["text"]()
    assert "Trust +2" in chat_dialog.kwargs["text"]()
    assert hasattr(chat_dialog.kwargs["text_inputs"], "message")
    assert chat_dialog.show_kwargs == {}
    assert len(notifications) == notification_count
    chat_dialog.accepted = True
    chat_dialog.text_input_responses = {"message": "Do you?"}
    chat_dialog.listener(chat_dialog)
    assert submitted[-1] == (
        pie_interaction.sim,
        pie_interaction.target,
        "Do you?",
        chat_dialog.kwargs["text"](),
    )

    sim_chat = type("native_NPC_social", (), {})
    target = type(
        "Target",
        (),
        {"commodity_flags": frozenset(("social",)), "is_selectable": False},
    )()
    interaction = SimpleNamespace(
        _aop=SimpleNamespace(
            super_affordance=type("SocialSuperInteraction", (), {}),
            super_interaction=None,
        ),
        affordance=sim_chat,
        context=SimpleNamespace(sim="actor-context"),
        target=target,
    )
    target.potential_interactions = lambda _context: [
        SimpleNamespace(affordance=interaction._aop.super_affordance)
    ]

    request = SimpleNamespace(object_list=None, interactions_to_invalidate=[])
    actor = SimpleNamespace(
        autonomy_component=SimpleNamespace(_create_autonomy_request=lambda: request)
    )
    relationship_bits = set()
    has_met = type("has_met", (), {})
    tracker = SimpleNamespace(
        has_bit=lambda target_id, bit: (target_id, bit) in relationship_bits,
        add_relationship_bit=lambda target_id, bit: relationship_bits.add((target_id, bit)),
    )
    bella = SimpleNamespace(
        sim_id="bella",
        get_sim_instance=lambda: actor,
        relationship_tracker=tracker,
    )
    mortimer = SimpleNamespace(sim_id="mortimer", get_sim_instance=lambda: target)
    target.sim_info = mortimer
    sims = [bella, mortimer]
    payloads = []
    monkeypatch.setattr(agent, "instanced_npc_infos", lambda: sims)

    def find_best_action(selected_request):
        motives = frozenset(("social",))
        if selected_request.object_list:
            for candidate in selected_request.object_list:
                candidate.commodity_flags & motives
        affordances = getattr(selected_request, "affordance_list", None)
        if affordances:
            return FakeAffordanceObjectPair(
                affordances[0],
                selected_request.object_list[0],
                interaction._aop.super_affordance,
                None,
                push_super_on_prepare=True,
            )
        return interaction

    services.autonomy_service = lambda: SimpleNamespace(
        find_best_action=find_best_action
    )
    monkeypatch.setattr(
        agent,
        "sim_info_payload",
        lambda sim: {"id": sim.sim_id, "name": sim.sim_id.title()},
    )
    monkeypatch.setattr(agent, "relationship_payload", lambda *_args: {})
    monkeypatch.setattr(agent, "current_location", lambda: "Goth Manor")
    monkeypatch.setattr(
        agent,
        "post_json",
        lambda path, payload, timeout=None: payloads.append((path, payload))
        or {
            "decision_id": "decision-1",
            "suggested_action": "friendly_chat",
        },
    )
    monkeypatch.setattr(
        agent.threading,
        "Thread",
        lambda target: SimpleNamespace(daemon=False, start=target),
    )

    agent.autonomous_tick(None)
    agent._AUTONOMY_IN_FLIGHT = True
    agent.autonomous_tick(None)

    assert len(payloads) == 1
    assert payloads[0][0] == "/autonomous"
    assert payloads[0][1]["speaker"]["id"] == "bella"
    assert payloads[0][1]["listener"]["id"] == "mortimer"
    assert payloads[0][1]["event"] == {
        "type": "autonomous_social",
        "source": "sim_alarm",
    }

    social_mixer_base = type("SocialMixerInteraction", (), {})
    mixer = type(
        "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
        (social_mixer_base,),
        {},
    )
    apologize = type("mixer_social_Apologize_targeted_friendly_lowScore", (), {})
    flirt = type(
        "mixer_social_ComplimentAppearance_targeted_romance_alwaysOn", (), {}
    )
    interaction._aop.super_affordance.all_affordances_gen = classmethod(
        lambda _cls, **_kwargs: iter((mixer, apologize, flirt))
    )
    infos = {
        "bella": bella,
        "mortimer": mortimer,
    }
    monkeypatch.setattr(agent, "find_sim_info_by_id", infos.get)
    unrelated_social = type("socialSuperInteraction_CarryLetOut", (), {})
    custom_social = type("BC:Slap Child Social SuperInteraction", (), {})
    manager = SimpleNamespace(
        get=lambda _key: None,
        types={
            1: unrelated_social,
            3: custom_social,
            4: mixer,
            5: sim_chat,
            6: apologize,
            7: flirt,
            8: has_met,
        },
    )
    monkeypatch.setattr(
        agent.services, "get_instance_manager", lambda _type: manager, raising=False
    )

    assert agent.find_action_affordance("friendly_chat") is mixer
    assert agent.find_action_affordance("apologize") is apologize
    assert agent.find_action_affordance("flirt") is flirt
    assert agent.find_action_affordance("argue") is None
    assert agent.AVAILABLE_ACTIONS == ["friendly_chat", "apologize", "flirt"]
    assert agent.social_tuning_names("askaboutday") == [
        "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn"
    ]

    agent.process_autonomy_responses(None)

    assert len(mapped_aops) == 1
    assert mapped_aops[0].affordance is mixer
    assert mapped_aops[0].target is target
    assert mapped_aops[0].push_super_on_prepare is True
    assert len(executed) == 1
    assert executed[0] is not interaction
    assert executed[0].affordance is mixer
    assert len(payloads) == 1

    executed[0].finishing_type = "FinishingType.NATURAL"
    executed[0].finishing_callback(executed[0])
    assert payloads[1] == (
        "/action-result",
        {
            "decision_id": "decision-1",
            "action": "friendly_chat",
            "status": "succeeded",
            "reason": None,
            "changes": [],
        },
    )
    assert agent._AUTONOMY_IN_FLIGHT is False

    agent.execute_sims_action(
        payloads[0][1],
        {"decision_id": "decision-2", "suggested_action": "apologize"},
        interaction,
    )
    assert mapped_aops[1].affordance is apologize
    assert len(payloads) == 2

    executed[1].finishing_type = "FinishingType.DISPLACED"
    executed[1].finishing_callback(executed[1])
    assert payloads[2] == (
        "/action-result",
        {
            "decision_id": "decision-2",
            "action": "apologize",
            "status": "failed",
            "reason": "FinishingType.DISPLACED",
            "changes": [],
        },
    )
    player_payload = dict(payloads[0][1])
    player_payload["speaker"], player_payload["listener"] = (
        player_payload["listener"],
        player_payload["speaker"],
    )
    player_data = {
        "decision_id": "decision-3",
        "animation": "friendly_chat",
        "dialogue": "How is your day?",
        "emotion": "happy",
        "intent": "greet",
        "relationship": {},
        "_empneon_payload": player_payload,
    }
    agent.show_empneon_chat_result(
        pie_interaction.sim,
        pie_interaction.target,
        player_data,
        None,
    )
    assert len(mapped_aops) == 3
    assert mapped_aops[2].affordance is mixer
    assert mapped_aops[2].push_super_on_prepare is True
    assert executed[2].affordance is mixer
    assert len(payloads) == 3
    assert relationship_bits == {("mortimer", has_met)}

    executed[2].finishing_type = "FinishingType.NATURAL"
    executed[2].finishing_callback(executed[2])
    assert payloads[3][0] == "/action-result"
    assert payloads[3][1]["decision_id"] == "decision-3"
    assert payloads[3][1]["status"] == "succeeded"

    bad_parent = type("EmpneonSocialInteraction", (), {})
    bad_parent.all_affordances_gen = classmethod(
        lambda _cls, **_kwargs: iter((mixer,))
    )
    failed_factories.add(bad_parent)
    target.potential_interactions = lambda _context: [
        SimpleNamespace(affordance=bad_parent),
        SimpleNamespace(affordance=interaction._aop.super_affordance),
    ]
    agent.execute_sims_action(
        player_payload,
        {"decision_id": "decision-4", "animation": "friendly_chat"},
        None,
    )
    assert mapped_aops[-1].affordance is mixer
    assert executed[-1].affordance is mixer
    assert relationship_bits == {("mortimer", has_met)}

    incompatible_parent = type("UnrelatedSocialSuperInteraction", (), {})
    incompatible_parent.all_affordances_gen = classmethod(
        lambda _cls, **_kwargs: iter(())
    )
    target.potential_interactions = lambda _context: [
        SimpleNamespace(affordance=incompatible_parent)
    ]
    agent.execute_sims_action(
        player_payload,
        {"decision_id": "decision-5", "animation": "friendly_chat"},
        None,
    )
    assert payloads[-1][0] == "/action-result"
    assert payloads[-1][1]["status"] == "failed"
    assert "friendly_chat" in payloads[-1][1]["reason"]
    assert "compatible social super-interaction" in payloads[-1][1]["reason"]
