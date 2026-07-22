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


def test_conversation_session_and_alarm_submit_without_overlap(monkeypatch) -> None:
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
    element_utils = ModuleType("element_utils")
    element_utils.sleep_until_next_tick_element = lambda: "next-tick"

    def run_child(_timeline, element):
        yield element

    element_utils.run_child = run_child
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
    failed_tests = set()


    class FakeMappedInteraction:
        def __init__(self, affordance):
            self.affordance = affordance
            self.finishing_type = ""
            self.finishing_callback = None
            self.canceled = False

        def register_on_finishing_callback(self, callback):
            self.finishing_callback = callback

        def cancel(self):
            self.canceled = True

    class FakeAffordanceObjectPair:
        def __init__(self, affordance, target, super_affordance, super_interaction, **kwargs):
            self.affordance = affordance
            self.target = target
            self.super_affordance = super_affordance
            self.super_interaction = super_interaction
            self.__dict__.update(kwargs)
            mapped_aops.append(self)

        def test(self, _context):
            return self.super_affordance not in failed_tests

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
        "element_utils": element_utils,
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
        "sim_effects",
        "sim_sentiments",
        "sim_moodlets",
        "sim_aspiration",
        "sim_career",
        "sim_skills",
        "sim_household",
    ):
        assert hasattr(agent, probe)

    primitive_values = ("RawModBuff", 73, False, None)
    primitive_items = [
        agent.native_game_item(value, "moodlet") for value in primitive_values
    ]
    assert [
        (item["label"], item["id"]) for item in primitive_items
    ] == [(value, value) for value in primitive_values]
    assert agent.raw_enum_text(0) == "0"

    class BrokenBuff:
        @property
        def buff_type(self):
            raise RuntimeError("broken mod buff")

    isolated_effects = agent.sim_effects(
        SimpleNamespace(
            buff_component=SimpleNamespace(
                get_all_buffs=lambda: ["FirstBuff", BrokenBuff(), "LastBuff"]
            )
        )
    )
    assert [item["label"] for item in isolated_effects] == [
        "FirstBuff",
        "LastBuff",
    ]
    fallback_target = type("FallbackTarget", (), {"sim_id": "fallback-target"})()
    fallback_sentiment = type(
        "FallbackSentiment",
        (),
        {"guid64": "fallback-sentiment", "polarity": "positive"},
    )
    fallback_records = agent.sim_sentiments(
        SimpleNamespace(
            sentiment_tracker=SimpleNamespace(
                get_all_sentiments=lambda: None,
                sentiments={
                    fallback_target: SimpleNamespace(sentiment=fallback_sentiment)
                },
            )
        )
    )
    assert fallback_records == [
        {
            "kind": "sentiment",
            "label": "FallbackSentiment",
            "id": "fallback-sentiment",
            "polarity": "positive",
            "target_id": "fallback-target",
        }
    ]
    all_moodlet_labels = [f"Moodlet{index}" for index in range(25)]
    uncapped_payload = agent.sim_info_payload(
        SimpleNamespace(
            buff_component=SimpleNamespace(
                get_all_buffs=lambda: all_moodlet_labels
            )
        )
    )
    assert uncapped_payload["moodlets"] == all_moodlet_labels
    assert [
        item["label"] for item in uncapped_payload["native"]["moodlets"]
    ] == all_moodlet_labels

    hunger = SimpleNamespace(
        stat_type=type("motive_Hunger", (), {}),
        get_value=lambda: -40,
    )
    internal_stat = SimpleNamespace(
        stat_type=type("commodity_burnout_mentaltracker", (), {}),
        get_value=lambda: 5,
    )
    cooking = SimpleNamespace(
        stat_type=type("Cooking", (), {}),
        get_value=lambda: 7,
    )
    inspired = type(
        "Inspired", (), {"guid64": "buff-inspired", "polarity": "unknown"}
    )
    modded_aurora = type(
        "ModdedAuroraState", (), {"guid64": "buff-modded", "polarity": "unknown"}
    )
    adoring = type(
        "Adoring", (), {"guid64": "sentiment-adoring", "polarity": "positive"}
    )
    bernard = type("SentimentTarget", (), {"sim_id": "bernard"})()
    outgoing = SimpleNamespace(
        name="Outgoing",
        guid64=101,
        trait_description="Enjoys socializing and speaks confidently.",
    )
    rich_info = SimpleNamespace(
        sim_id="bella",
        full_name="Bella",
        gender=SimpleNamespace(name="FEMALE", value=1),
        age=SimpleNamespace(name="YOUNGADULT", value=5),
        get_mood=lambda: type("mood_uncomfortable", (), {}),
        trait_tracker=SimpleNamespace(equipped_traits=[outgoing]),
        commodity_tracker=SimpleNamespace(
            get_all_commodities=lambda: [hunger, internal_stat]
        ),
        buff_component=SimpleNamespace(
            get_all_buffs=lambda: [
                SimpleNamespace(buff_type=inspired),
                SimpleNamespace(buff_type=modded_aurora),
            ]
        ),
        sentiment_tracker=SimpleNamespace(
            sentiments={bernard: SimpleNamespace(sentiment=adoring)}
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
    assert rich_payload["identity"] == {
        "gender": {"key": "female", "label": "Female"},
        "age": {
            "kind": "life_stage",
            "value": "young_adult",
            "label": "Young Adult",
        },
        "traits": [
            {
                "id": "101",
                "label": "Outgoing",
                "description": "Enjoys socializing and speaks confidently.",
            }
        ],
    }
    assert rich_payload["native"]["identity"] == {
        "gender": "FEMALE",
        "age": "YOUNGADULT",
    }
    assert rich_payload.get("age") is None
    assert rich_payload["traits"] == ["Outgoing"]
    assert rich_payload["current_mood"] == "uncomfortable"
    assert rich_payload["needs"] == {"hunger": -40}
    assert rich_payload["moodlets"] == ["Inspired", "ModdedAuroraState"]
    assert rich_payload["effects"] == [
        {
            "kind": "moodlet",
            "label": "Inspired",
            "id": "buff-inspired",
            "polarity": "unknown",
        },
        {
            "kind": "moodlet",
            "label": "ModdedAuroraState",
            "id": "buff-modded",
            "polarity": "unknown",
        },
        {
            "kind": "sentiment",
            "label": "Adoring",
            "id": "sentiment-adoring",
            "polarity": "positive",
            "target_id": "bernard",
        },
    ]
    assert rich_payload["native"]["mood"] == rich_payload["current_mood"]
    assert rich_payload["native"]["buffs"][1]["label"] == "ModdedAuroraState"
    assert rich_payload["native"]["sentiments"][0]["target_id"] == "bernard"
    assert rich_payload["aspiration"] == "MasterChef"
    assert rich_payload["career"] == "Painter"
    assert rich_payload["skills"] == {"Cooking": 7}
    assert rich_payload["household"] == {"id": "42", "name": "Goth Household"}

    starving = SimpleNamespace(
        stat_type=type("motive_Hunger", (), {}),
        get_value=lambda: -120,
    )
    assert agent.sim_needs(
        SimpleNamespace(
            commodity_tracker=SimpleNamespace(
                get_all_commodities=lambda: [starving]
            )
        )
    ) == {"hunger": -100}

    class BrokenTrait:
        name = "BrokenTrait"

        @property
        def trait_description(self):
            raise RuntimeError("broken mod trait")

    modded_payload = agent.sim_info_payload(
        SimpleNamespace(
            gender="ROBOT",
            age=999,
            trait_tracker=SimpleNamespace(
                equipped_traits=[outgoing, BrokenTrait()]
            ),
        )
    )
    assert modded_payload["identity"] == {
        "gender": {"key": "unknown", "label": "Unknown"},
        "age": {
            "kind": "life_stage",
            "value": "unknown",
            "label": "Unknown",
        },
        "traits": [
            {
                "id": "101",
                "label": "Outgoing",
                "description": "Enjoys socializing and speaks confidently.",
            }
        ],
    }
    assert modded_payload["native"]["identity"] == {
        "gender": "ROBOT",
        "age": "999",
    }
    assert modded_payload["traits"] == ["Outgoing"]

    method_info = SimpleNamespace(
        aspiration_tracker=SimpleNamespace(
            get_primary_aspiration=lambda: type("Bodybuilder", (), {})
        )
    )
    assert agent.sim_aspiration(method_info) == "Bodybuilder"

    friendship_track = type("LTR_Friendship_Main", (), {})
    romance_track = type("LTR_Romance_Main", (), {})
    attraction_track = type("ATTRACTION_MAIN", (), {})
    track_manager = SimpleNamespace(
        types={1: friendship_track, 2: romance_track, 358555: attraction_track}
    )
    agent.services.get_instance_manager = lambda _resource_type: track_manager
    scores = {friendship_track: -20, romance_track: 15, attraction_track: 75}
    source_info = SimpleNamespace(
        relationship_tracker=SimpleNamespace(
            get_relationship_score=lambda _target, track=None: scores[track]
        )
    )
    target_info = SimpleNamespace(sim_id="mortimer")
    relationship = agent.relationship_payload(source_info, target_info)
    assert relationship["friendship"] == -20
    assert relationship["romance"] == 15
    assert relationship["attraction"] == 0.75
    assert relationship["native"]["attraction"] == {
        "source": "sims4_lovestruck",
        "value": 75.0,
        "label": "ATTRACTION_MAIN",
    }

    official_reader = agent._official_attraction

    def sim(sim_id):
        directed_scores = {("alice", "bob"): 75.0, ("bob", "alice"): -25.0}
        return SimpleNamespace(
            sim_id=sim_id,
            relationship_tracker=SimpleNamespace(
                get_relationship_score=lambda target, _track: directed_scores[
                    (sim_id, str(getattr(target, "sim_id", target)))
                ]
            ),
        )

    assert official_reader(sim("alice"), sim("bob"))["value"] == 0.75
    assert official_reader(sim("bob"), sim("alice"))["value"] == -0.25

    monkeypatch.setattr(
        agent,
        "_wickedwhims_attraction",
        lambda _source, _target: {
            "value": 2 / 3,
            "native": {"source": "wickedwhims", "value": 2, "label": "HIGH"},
        },
    )
    monkeypatch.setattr(
        agent,
        "_official_attraction",
        lambda _source, _target: {
            "value": -0.5,
            "native": {
                "source": "sims4_lovestruck",
                "value": -50,
                "label": "ATTRACTION_MAIN",
            },
        },
    )
    assert agent.attraction_payload(source_info, target_info) == {
        "value": 2 / 3,
        "native": {"source": "wickedwhims", "value": 2, "label": "HIGH"},
    }

    monkeypatch.setattr(agent, "_wickedwhims_attraction", lambda *_args: None)
    assert agent.attraction_payload(source_info, target_info) == {
        "value": -0.5,
        "native": {
            "source": "sims4_lovestruck",
            "value": -50,
            "label": "ATTRACTION_MAIN",
        },
    }

    monkeypatch.setattr(
        agent,
        "_wickedwhims_attraction",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("incompatible mod")),
    )
    assert agent.attraction_payload(source_info, target_info)["value"] == -0.5
    assert agent._attraction_record("bad", float("nan"), 1, "bad") is None
    assert agent._attraction_record("bad", 1.1, 1, "bad") is None

    monkeypatch.setattr(agent, "_official_attraction", lambda *_args: None)
    assert agent.attraction_payload(source_info, target_info) is None

    relationship_queries = []
    relationship_output = []
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
            or {
                "relationship": {
                    "direction": {"source_id": "cam-id", "target_id": "bella"},
                    "native": {
                        "friendship": 7,
                        "romance": 12,
                        "attraction": {
                            "normalized": 2 / 3,
                            "source": "wickedwhims",
                            "value": 2,
                            "label": "HIGH",
                        },
                    },
                    "empneon": {"trust": 51},
                }
            },
        )
        command_patch.setattr(
            agent,
            "out",
            lambda _connection, text: relationship_output.append(text),
        )
        agent.ai_relationship("Cam", "Sadya")
    assert relationship_queries == [
        ("/relationship", {"sim_id": "cam-id", "target_id": "bella"})
    ]
    assert relationship_output == [
        "relationship Cam Sadya -> Bella: Sims friendship 7, Sims romance 12, "
        "Sims attraction +0.67 (wickedwhims: HIGH), Empneon trust 51"
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
        lambda session, message: submitted.append((session, message)),
    )
    pie_interaction = agent.EmpneonSocialInteraction()
    pie_interaction.sim = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="alice", full_name="Alice")
    )
    pie_interaction.target = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="bob", full_name="Bob")
    )
    runner = pie_interaction._run_interaction_gen("timeline")
    assert next(runner) == "next-tick"
    session = agent._CONVERSATION_SESSIONS["alice"]
    assert session.phase == "input"
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
    assert dialog.kwargs["title"]() == "Empneon Social with Bob"
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
    assert session.phase == "waiting_for_backend"
    assert submitted == [(session, "Remember our promise?")]
    assert next(runner) == "next-tick"
    with monkeypatch.context() as acknowledgement_patch:
        acknowledgement_patch.setattr(
            agent,
            "report_dialogue_delivery",
            lambda *_args, **_kwargs: agent._SESSION_EVENTS.append(
                (session.id, session.turn_id, "dialogue_displayed", None)
            ),
        )
        session.accept_backend_result(
            session.turn_id,
            {
                "decision_id": "decision-session",
                "dialogue": "I remember.",
                "suggested_action": "none",
            },
            None,
        )
    agent.process_autonomy_responses(None)
    assert session.phase == "showing_response"
    response_dialog = dialogs[-1]
    response_dialog.accepted = False
    response_dialog.listener(response_dialog)
    try:
        next(runner)
    except StopIteration as finished:
        assert finished.value is True
    else:
        raise AssertionError("closed session kept the interaction alive")
    assert "alice" not in agent._CONVERSATION_SESSIONS

    for canceled_by in ("queue_cancel", "actor_missing", "target_missing"):
        canceled_interaction = agent.EmpneonSocialInteraction()
        canceled_interaction.sim = SimpleNamespace(
            sim_info=SimpleNamespace(sim_id=canceled_by, full_name="Alice")
        )
        canceled_interaction.target = SimpleNamespace(
            sim_info=SimpleNamespace(sim_id="bob", full_name="Bob")
        )
        canceled_runner = canceled_interaction._run_interaction_gen("timeline")
        assert next(canceled_runner) == "next-tick"
        canceled_session = agent._CONVERSATION_SESSIONS[canceled_by]
        canceled_session.turn_id = 1
        if canceled_by == "queue_cancel":
            canceled_runner.close()
        elif canceled_by == "actor_missing":
            canceled_session.actor = None
        else:
            canceled_session.target = None
        if canceled_by != "queue_cancel":
            try:
                next(canceled_runner)
            except StopIteration:
                pass
            else:
                raise AssertionError("missing participant kept the session alive")
        dialog_count = len(dialogs)
        agent._ACTION_RESULT_OUTBOX[:] = []
        agent._ACTION_RESULT_RESPONSES[:] = []
        late_reports = []
        with monkeypatch.context() as late_patch:
            late_patch.setattr(
                agent,
                "post_json",
                lambda path, payload, timeout=None: late_reports.append((path, payload)),
            )
            late_patch.setattr(
                agent.threading,
                "Thread",
                lambda target: SimpleNamespace(daemon=False, start=target),
            )
            agent._CHAT_RESPONSES.append(
                (
                    canceled_session.id,
                    1,
                    {
                        "decision_id": "late-decision",
                        "suggested_action": "friendly_chat",
                    },
                    None,
                )
            )
            agent.process_autonomy_responses(None)
            for _attempt in range(10):
                if late_reports:
                    break
                agent.process_autonomy_responses(None)
        assert len(dialogs) == dialog_count
        assert late_reports == [
            (
                "/action-result",
                {
                    "decision_id": "late-decision",
                    "action": "friendly_chat",
                    "status": "failed",
                    "reason": "Empneon Social canceled",
                    "changes": [],
                },
            )
        ], agent._ACTION_RESULT_OUTBOX

    displayed_cancel_interaction = agent.EmpneonSocialInteraction()
    displayed_cancel_interaction.sim = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="displayed-cancel", full_name="Alice")
    )
    displayed_cancel_interaction.target = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="bob", full_name="Bob")
    )
    displayed_cancel_runner = displayed_cancel_interaction._run_interaction_gen(
        "timeline"
    )
    assert next(displayed_cancel_runner) == "next-tick"
    displayed_cancel_session = agent._CONVERSATION_SESSIONS["displayed-cancel"]
    displayed_cancel_session.turn_id = 1
    displayed_cancel_session.phase = "waiting_for_backend"
    with monkeypatch.context() as displayed_cancel_patch:
        displayed_cancel_patch.setattr(
            agent, "report_dialogue_delivery", lambda *_args, **_kwargs: None
        )
        displayed_cancel_session.accept_backend_result(
            1,
            {
                "decision_id": "displayed-cancel-decision",
                "dialogue": "Wait for me.",
                "suggested_action": "friendly_chat",
            },
            None,
        )
    assert displayed_cancel_session.phase == "showing_response"
    cancel_dialog_count = len(dialogs)
    displayed_cancel_reports = []
    with monkeypatch.context() as displayed_cancel_patch:
        displayed_cancel_patch.setattr(
            agent,
            "post_json",
            lambda path, payload, timeout=None: displayed_cancel_reports.append(
                (path, payload)
            )
            or payload,
        )
        displayed_cancel_patch.setattr(
            agent.threading,
            "Thread",
            lambda target: SimpleNamespace(daemon=False, start=target),
        )
        displayed_cancel_runner.close()
        agent._SESSION_EVENTS.append(
            (
                displayed_cancel_session.id,
                1,
                "dialogue_displayed",
                None,
            )
        )
        agent.process_autonomy_responses(None)
    assert len(dialogs) == cancel_dialog_count
    assert displayed_cancel_reports == [
        (
            "/action-result",
            {
                "decision_id": "displayed-cancel-decision",
                "action": "friendly_chat",
                "status": "failed",
                "reason": "Empneon Social canceled",
                "changes": [],
            },
        )
    ]

    notification_count = len(notifications)
    delivery_reports = []
    with monkeypatch.context() as delivery_patch:
        delivery_patch.setattr(
            agent,
            "post_json",
            lambda path, payload, timeout=90: delivery_reports.append(
                (path, payload, timeout)
            )
            or {"decision_id": payload["decision_id"], "status": "displayed"},
        )

        class ImmediateThread:
            daemon = False

            def __init__(self, target):
                self.target = target

            def start(self):
                self.target()

        delivery_patch.setattr(agent.threading, "Thread", ImmediateThread)
        display_session = agent.EmpneonConversationSession(
            pie_interaction, pie_interaction.sim, pie_interaction.target
        )
        display_session.turn_id = 1
        display_session.phase = "showing_response"
        display_session.transcript = "Alice: Remember our promise?"
        agent._CONVERSATION_SESSIONS["display-session"] = display_session
        agent.show_empneon_chat_result(
            display_session,
            {
                "decision_id": "decision-displayed",
                "dialogue": "I remember.",
                "emotion": "warm",
                "intent": "reassure",
                "response_category": "friendly",
                "tone_tags": ["warm"],
                "trust_delta": 2,
                "suggested_action": "none",
            },
            None,
        )
    chat_dialog = dialogs[-1]
    assert chat_dialog.kwargs["title"]() == "Bob says:"
    assert "Alice: Remember our promise?" in chat_dialog.kwargs["text"]()
    assert "Bob: I remember." in chat_dialog.kwargs["text"]()
    assert "Category: friendly" in chat_dialog.kwargs["text"]()
    assert "Tone: warm" in chat_dialog.kwargs["text"]()
    assert "Empneon trust +2" in chat_dialog.kwargs["text"]()
    assert hasattr(chat_dialog.kwargs["text_inputs"], "message")
    assert chat_dialog.show_kwargs == {}
    assert len(notifications) == notification_count
    assert delivery_reports == [
        (
            "/dialogue-result",
            {"decision_id": "decision-displayed", "status": "displayed"},
            10,
        )
    ]
    missing_actor_session = agent.EmpneonConversationSession(
        pie_interaction, None, pie_interaction.target
    )
    assert agent.show_empneon_message_dialog(missing_actor_session, "not shown") is False
    assert delivery_reports == [
        (
            "/dialogue-result",
            {"decision_id": "decision-displayed", "status": "displayed"},
            10,
        )
    ]
    chat_dialog.accepted = True
    chat_dialog.text_input_responses = {"message": "Do you?"}
    display_session.dialogue_acknowledged = True
    chat_dialog.listener(chat_dialog)
    assert submitted[-1] == (display_session, "Do you?")

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
    monkeypatch.setattr(
        agent,
        "relationship_payload",
        lambda source, target: {
            "direction": "{}-to-{}".format(
                source.sim_id, getattr(target, "sim_id", "unknown")
            )
        },
    )
    monkeypatch.setattr(agent, "current_location", lambda: "Goth Manor")
    social_mixer_base = type("SocialMixerInteraction", (), {})
    mixer = type(
        "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
        (social_mixer_base,),
        {},
    )
    funny = type("mixer_social_TellJoke_targeted_Funny_alwaysOn", (), {})
    romance = type(
        "mixer_social_ComplimentAppearance_targeted_romance_alwaysOn", (), {}
    )
    mean = type("mixer_social_Insult_targeted_mean_alwaysOn", (), {})
    mischief = type(
        "mixer_social_LieAboutCareer_targeted_mischief_alwaysOn", (), {}
    )
    apologize = type("mixer_social_Apologize_targeted_friendly_lowScore", (), {})
    monkeypatch.setattr(
        agent,
        "loaded_interaction_tunings",
        lambda: (mixer, funny, romance, mean, mischief, apologize),
    )
    held_payload = agent.chat_payload_for_target(
        SimpleNamespace(sim_info=SimpleNamespace(sim_id="mortimer")),
        SimpleNamespace(sim_id="bella"),
        "Would you like to go on a date?",
        "pie_menu",
    )
    assert held_payload["available_response_categories"] == [
        "friendly",
        "funny",
        "romance",
        "mean",
        "mischief",
    ]
    assert held_payload["relationship"] == {"direction": "bella-to-mortimer"}
    assert held_payload["listener_relationship"] == {
        "direction": "mortimer-to-bella"
    }
    assert agent.NATIVE_SOCIAL_TUNINGS == {
        "social.friendly": "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
        "social.funny": "mixer_social_TellJoke_targeted_Funny_alwaysOn",
        "social.romance": "mixer_social_ComplimentAppearance_targeted_romance_alwaysOn",
        "social.mean": "mixer_social_Insult_targeted_mean_alwaysOn",
        "social.mischief": "mixer_social_LieAboutCareer_targeted_mischief_alwaysOn",
        "friendly_chat": "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
        "apologize": "mixer_social_Apologize_targeted_friendly_lowScore",
        "flirt": "mixer_social_ComplimentAppearance_targeted_romance_alwaysOn",
    }
    with monkeypatch.context() as missing_mean:
        missing_mean.setattr(
            agent,
            "loaded_interaction_tunings",
            lambda: (mixer, funny, romance, mischief, apologize),
        )
        assert agent.available_social_categories() == [
            "friendly",
            "funny",
            "romance",
            "mischief",
        ]
    monkeypatch.setattr(
        agent,
        "post_json",
        lambda path, payload, timeout=None: payloads.append((path, payload))
        or (
            {"decision_id": "decision-1", "suggested_action": "friendly_chat"}
            if path == "/autonomous"
            else {"decision_id": payload.get("decision_id"), "status": "displayed"}
        ),
    )
    monkeypatch.setattr(
        agent.threading,
        "Thread",
        lambda target: SimpleNamespace(daemon=False, start=target),
    )

    def pump_outbox():
        for _attempt in range(100):
            agent.process_autonomy_responses(None)
            if not agent._ACTION_RESULT_OUTBOX and not agent._ACTION_RESULT_RESPONSES:
                break

    assert agent._outbox_delay(1000000) == 32

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

    interaction._aop.super_affordance.all_affordances_gen = classmethod(
        lambda _cls, **_kwargs: iter(
            (mixer, apologize, funny, romance, mean, mischief)
        )
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
            7: romance,
            8: has_met,
            9: funny,
            10: mean,
            11: mischief,
        },
    )
    monkeypatch.setattr(
        agent.services, "get_instance_manager", lambda _type: manager, raising=False
    )

    assert agent.find_action_affordance("friendly_chat") is mixer
    assert agent.find_action_affordance("apologize") is apologize
    assert agent.find_action_affordance("flirt") is romance
    assert agent.find_action_affordance("social.friendly") is mixer
    assert agent.find_action_affordance("social.funny") is funny
    assert agent.find_action_affordance("social.romance") is romance
    assert agent.find_action_affordance("social.mean") is mean
    assert agent.find_action_affordance("social.mischief") is mischief
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

    with monkeypatch.context() as unrelated_patch:
        unrelated_patch.setattr(
            agent,
            "post_json",
            lambda _path, body, timeout=None: body,
        )
        agent.report_action_result(
            "decision-unrelated",
            "friendly_chat",
            "failed",
            "player session canceled",
        )
        pump_outbox()
    assert agent._AUTONOMY_IN_FLIGHT is True

    executed[0].finishing_type = "FinishingType.NATURAL"
    executed[0].finishing_callback(executed[0])
    pump_outbox()
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
    pump_outbox()
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
    player_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    player_session.turn_id = 1
    player_session.phase = "showing_response"
    agent._CONVERSATION_SESSIONS["alice"] = player_session
    callback_order = []
    original_post_json = agent.post_json
    delayed_workers = []

    class DelayedThread:
        daemon = False

        def __init__(self, target):
            delayed_workers.append(target)

        def start(self):
            pass

    def ordered_post_json(path, payload, timeout=None):
        if path == "/dialogue-result":
            callback_order.append("displayed")
        elif path == "/action-result":
            callback_order.append("native_result_posted")
        return original_post_json(path, payload, timeout=timeout)

    monkeypatch.setattr(agent, "post_json", ordered_post_json)
    monkeypatch.setattr(agent.threading, "Thread", DelayedThread)
    agent.show_empneon_chat_result(player_session, player_data, None)
    assert len(delayed_workers) == 1
    assert len(payloads) == 3
    assert agent._SESSION_EVENTS == []
    assert agent._AUTONOMY_RESPONSES == []
    second_turn_dialog = dialogs[-1]
    second_turn_dialog.accepted = True
    second_turn_dialog.text_input_responses = {"message": "And tomorrow?"}
    second_turn_dialog.listener(second_turn_dialog)
    assert player_session.phase == "showing_response"
    assert len(mapped_aops) == 2

    delayed_workers.pop(0)()
    assert payloads[3] == (
        "/dialogue-result",
        {"decision_id": "decision-3", "status": "displayed"},
    )
    assert agent._AUTONOMY_RESPONSES == []
    assert len(mapped_aops) == 2
    monkeypatch.setattr(
        agent.threading,
        "Thread",
        lambda target: SimpleNamespace(daemon=False, start=target),
    )
    agent.process_autonomy_responses(None)
    assert player_session.phase == "running_native_action"
    assert player_session.pending_decision == ("decision-3", "friendly_chat")
    assert len(mapped_aops) == 3
    assert mapped_aops[2].affordance is mixer
    assert mapped_aops[2].push_super_on_prepare is True
    assert executed[2].affordance is mixer
    assert relationship_bits == {("mortimer", has_met)}

    worker_dialog_count = len(dialogs)
    executed[2].finishing_type = "FinishingType.NATURAL"
    executed[2].finishing_callback(executed[2])
    pump_outbox()
    assert payloads[4][0] == "/action-result"
    assert payloads[4][1]["decision_id"] == "decision-3"
    assert payloads[4][1]["status"] == "succeeded"
    assert len(dialogs) == worker_dialog_count
    original_after_native_action = player_session.after_native_action

    def after_native_action(turn_id):
        callback_order.append("native_finished")
        return original_after_native_action(turn_id)

    player_session.after_native_action = after_native_action
    monkeypatch.setattr(
        agent,
        "submit_empneon_chat",
        lambda _session, _message: callback_order.append("second_submitted"),
    )
    agent.process_autonomy_responses(None)
    assert player_session.turn_id == 2
    assert player_session.phase == "waiting_for_backend"
    assert callback_order == [
        "displayed",
        "native_result_posted",
        "native_finished",
        "second_submitted",
    ]

    romance_reports = []
    with monkeypatch.context() as romance_patch:
        romance_patch.setattr(
            agent,
            "post_json",
            lambda path, body, timeout=None: romance_reports.append((path, body)) or body,
        )
        romance_patch.setattr(
            agent,
            "relationship_payload",
            lambda _source, _target: {"friendship": 0, "romance": 7},
        )
        romance_session = agent.EmpneonConversationSession(
            pie_interaction, pie_interaction.sim, pie_interaction.target
        )
        romance_session.turn_id = 1
        romance_session.phase = "showing_response"
        romance_session.dialogue_acknowledged = True
        romance_session.response_choice_ready = True
        romance_session.response_data = {
            "decision_id": "decision-social-romance",
            "suggested_action": "social.romance",
            "_empneon_payload": dict(
                player_payload,
                relationship={"friendship": 0, "romance": 0},
            ),
        }
        agent._CONVERSATION_SESSIONS["social-romance"] = romance_session
        interaction._aop.super_affordance.all_affordances_gen = classmethod(
            lambda _cls, **_kwargs: iter(
                (mixer, apologize, funny, mean, mischief)
            )
        )

        assert agent.continue_displayed_turn(romance_session) is True
        assert romance_session.phase == "running_native_action"
        assert mapped_aops[-1].affordance is romance
        romance_session.native_interaction.finishing_type = "FinishingType.NATURAL"
        romance_session.native_interaction.finishing_callback(
            romance_session.native_interaction
        )
        pump_outbox()

    assert romance_reports[-1] == (
        "/action-result",
        {
            "decision_id": "decision-social-romance",
            "action": "social.romance",
            "status": "succeeded",
            "reason": None,
            "changes": [
                {
                    "path": "relationship.romance",
                    "operation": "increment",
                    "value": 7,
                }
            ],
        },
    )
    interaction._aop.super_affordance.all_affordances_gen = classmethod(
        lambda _cls, **_kwargs: iter(
            (mixer, apologize, funny, romance, mean, mischief)
        )
    )

    zero_reports = []
    with monkeypatch.context() as zero_patch:
        zero_patch.setattr(
            agent,
            "post_json",
            lambda path, body, timeout=None: zero_reports.append((path, body)) or body,
        )
        zero_patch.setattr(
            agent,
            "relationship_payload",
            lambda _source, _target: {"friendship": 0, "romance": 0},
        )
        zero_session = agent.EmpneonConversationSession(
            pie_interaction, pie_interaction.sim, pie_interaction.target
        )
        zero_session.turn_id = 1
        zero_session.phase = "running_native_action"
        zero_session.pending_decision = ("decision-social-zero", "social.romance")
        agent._CONVERSATION_SESSIONS["social-zero"] = zero_session
        agent.execute_sims_action(
            dict(player_payload, relationship={"friendship": 0, "romance": 0}),
            {
                "decision_id": "decision-social-zero",
                "suggested_action": "social.romance",
            },
            None,
            session_id=zero_session.id,
            turn_id=1,
        )
        zero_session.native_interaction.finishing_type = "FinishingType.NATURAL"
        zero_session.native_interaction.finishing_callback(zero_session.native_interaction)
        pump_outbox()

    assert zero_reports[-1][1]["changes"] == []

    cancellation_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    cancellation_session.turn_id = 1
    cancellation_session.phase = "running_native_action"
    cancellation_session.pending_decision = ("decision-cancel-native", "social.mean")
    agent._CONVERSATION_SESSIONS["cancel-native"] = cancellation_session
    cancellation_reports = []
    with monkeypatch.context() as cancellation_patch:
        cancellation_patch.setattr(
            agent,
            "post_json",
            lambda path, body, timeout=None: cancellation_reports.append((path, body)) or body,
        )
        cancellation_patch.setattr(
            agent.threading,
            "Thread",
            lambda target: SimpleNamespace(daemon=False, start=target),
        )
        agent.execute_sims_action(
            player_payload,
            {
                "decision_id": "decision-cancel-native",
                "suggested_action": "social.mean",
            },
            None,
            session_id=cancellation_session.id,
            turn_id=1,
        )
        native_interaction = cancellation_session.native_interaction
        cancellation_session.close(canceled=True)
        agent._CONVERSATION_SESSIONS.pop("cancel-native")
        native_interaction.finishing_type = "FinishingType.NATURAL"
        native_interaction.finishing_callback(native_interaction)
        pump_outbox()
    assert native_interaction.canceled is True
    assert cancellation_reports == [
        (
            "/action-result",
            {
                "decision_id": "decision-cancel-native",
                "action": "social.mean",
                "status": "failed",
                "reason": "Empneon Social canceled",
                "changes": [],
            },
        )
    ]

    acknowledgement_failure_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    acknowledgement_failure_session.turn_id = 1
    acknowledgement_failure_session.phase = "showing_response"
    acknowledgement_failure_session.pending_decision = (
        "decision-ack-failure",
        "friendly_chat",
    )
    agent._CONVERSATION_SESSIONS["ack-failure"] = acknowledgement_failure_session
    action_count = len(mapped_aops)
    agent.finish_displayed_turn(
        acknowledgement_failure_session,
        {
            "decision_id": "decision-ack-failure",
            "suggested_action": "friendly_chat",
            "_empneon_payload": player_payload,
        },
        "Never submit",
    )
    monkeypatch.setattr(
        agent,
        "post_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("ack down")),
    )
    agent.report_dialogue_delivery(
        pie_interaction.sim,
        player_payload,
        {"decision_id": "decision-ack-failure"},
        queue_native=False,
        session_id=acknowledgement_failure_session.id,
        turn_id=1,
    )
    assert agent._SESSION_EVENTS[-1][2] == "dialogue_failed"
    agent.process_autonomy_responses(None)
    assert acknowledgement_failure_session.closed is True
    assert len(mapped_aops) == action_count

    lost_ack_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    lost_ack_session.turn_id = 1
    lost_ack_session.phase = "showing_response"
    lost_ack_session.pending_decision = ("decision-lost-ack", "none")
    lost_ack_session.response_data = {
        "decision_id": "decision-lost-ack",
        "suggested_action": "none",
    }
    lost_ack_session.response_choice_ready = True
    lost_ack_session.next_message = "Continue after retry"
    agent._CONVERSATION_SESSIONS["lost-ack"] = lost_ack_session
    monkeypatch.setattr(
        agent,
        "post_json",
        lambda *_args, **_kwargs: {
            "decision_id": "decision-lost-ack",
            "status": "already_displayed",
        },
    )
    agent.report_dialogue_delivery(
        pie_interaction.sim,
        player_payload,
        {"decision_id": "decision-lost-ack", "suggested_action": "none"},
        queue_native=False,
        session_id=lost_ack_session.id,
        turn_id=1,
    )
    assert agent._SESSION_EVENTS[-1][2] == "dialogue_displayed"
    lost_ack_submitted = []
    with monkeypatch.context() as lost_ack_patch:
        lost_ack_patch.setattr(
            agent,
            "submit_empneon_chat",
            lambda session, message: lost_ack_submitted.append((session, message)),
        )
        agent.process_autonomy_responses(None)
    assert lost_ack_session.closed is False
    assert lost_ack_session.canceled is False
    assert lost_ack_session.phase == "waiting_for_backend"
    assert lost_ack_submitted == [(lost_ack_session, "Continue after retry")]

    retry_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    retry_session.turn_id = 1
    retry_session.phase = "waiting_for_backend"
    dialog_count = len(dialogs)
    retry_session.accept_backend_result(1, None, "provider unavailable")
    assert retry_session.closed is False
    assert retry_session.phase == "input"
    assert len(dialogs) == dialog_count + 1
    assert dialogs[-1].kwargs["title"]() == "Empneon Social with Bob"

    failed_post_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    failed_post_session.turn_id = 1
    failed_post_session.phase = "running_native_action"
    failed_post_session.next_message = "Never submit"
    agent._CONVERSATION_SESSIONS["failed-post"] = failed_post_session
    monkeypatch.setattr(
        agent,
        "post_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("backend down")),
    )
    agent.report_action_result(
        "decision-post-failure",
        "friendly_chat",
        "succeeded",
        session_id=failed_post_session.id,
        turn_id=1,
    )
    pump_outbox()
    assert failed_post_session.closed is False
    assert failed_post_session.phase == "action_confirmation_failed"
    failed_item = next(
        item
        for item in agent._ACTION_RESULT_OUTBOX
        if item["body"]["decision_id"] == "decision-post-failure"
    )
    assert failed_item["paused"] is True
    retry_dialog = dialogs[-1]
    retry_dialog.accepted = True
    retry_dialog.listener(retry_dialog)
    assert failed_post_session.phase == "confirming_native_action"
    assert failed_item["paused"] is False
    monkeypatch.setattr(agent, "post_json", lambda _path, body, timeout=None: body)
    pump_outbox()
    agent.process_autonomy_responses(None)
    assert failed_post_session.phase == "waiting_for_backend"

    close_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    close_session.turn_id = 1
    close_session.phase = "running_native_action"
    close_session.pending_decision = ("decision-close", "friendly_chat")
    agent._CONVERSATION_SESSIONS["close-confirmation"] = close_session
    agent.report_action_result(
        "decision-close",
        "friendly_chat",
        "succeeded",
        session_id=close_session.id,
        turn_id=1,
    )
    close_item = agent._ACTION_RESULT_OUTBOX[-1]
    close_item["paused"] = True
    close_session.action_confirmation_failed(1, "backend down")
    close_dialog = dialogs[-1]
    close_dialog.accepted = False
    close_dialog.listener(close_dialog)
    assert close_session.closed is True
    assert close_item["paused"] is False

    retry_success_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    retry_success_session.turn_id = 1
    retry_success_session.phase = "running_native_action"
    retry_success_session.pending_decision = ("decision-retry", "friendly_chat")
    retry_success_session.action_result_started = True
    agent._CONVERSATION_SESSIONS["retry-success"] = retry_success_session
    retry_attempts = []
    retry_ticks = []

    def flaky_post(path, body, timeout=None):
        if body["decision_id"] == "decision-close":
            return body
        retry_attempts.append((path, body))
        retry_ticks.append(agent._RESPONSE_PUMP_TICK)
        if len(retry_attempts) < 3:
            raise RuntimeError("reply lost")
        return body

    monkeypatch.setattr(agent, "post_json", flaky_post)
    agent.report_action_result(
        "decision-retry",
        "friendly_chat",
        "failed",
        "interaction canceled",
        session_id=retry_success_session.id,
        turn_id=1,
    )
    agent._CONVERSATION_SESSIONS.pop("retry-success")
    pump_outbox()
    assert len(retry_attempts) == 3
    assert retry_ticks[1] - retry_ticks[0] >= 2
    assert retry_ticks[2] - retry_ticks[1] >= 4
    assert not any(
        item["body"]["decision_id"] == "decision-retry"
        for item in agent._ACTION_RESULT_OUTBOX
    )

    malformed_reports = []
    malformed_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    malformed_session.turn_id = 1
    malformed_session.phase = "running_native_action"
    agent._CONVERSATION_SESSIONS["malformed"] = malformed_session
    monkeypatch.setattr(
        agent,
        "post_json",
        lambda path, body, timeout=None: malformed_reports.append((path, body)) or body,
    )
    agent.execute_sims_action(
        None,
        {"decision_id": "decision-malformed", "suggested_action": "friendly_chat"},
        None,
        session_id=malformed_session.id,
        turn_id=1,
    )
    pump_outbox()
    assert malformed_reports[-1][0] == "/action-result"
    assert malformed_reports[-1][1]["status"] == "failed"
    agent.process_autonomy_responses(None)
    assert malformed_session.closed is True
    monkeypatch.setattr(agent, "post_json", original_post_json)

    console_calls = []
    console_output = []
    console_response = {
        "decision_id": "decision-console",
        "dialogue": "Console hello.",
        "suggested_action": "none",
        "relationship": {},
    }
    dialogue_attempts = {}

    def console_post(path, body, timeout=None):
        console_calls.append((path, body))
        if path == "/chat":
            return dict(console_response)
        if path == "/dialogue-result":
            decision_id = body["decision_id"]
            dialogue_attempts[decision_id] = dialogue_attempts.get(decision_id, 0) + 1
            if dialogue_attempts[decision_id] == 1:
                raise RuntimeError("dialogue response lost")
            return {"decision_id": body["decision_id"], "status": "displayed"}
        return {"decision_id": body["decision_id"], "status": body["status"]}

    def pump_dialogue_outbox():
        for _attempt in range(100):
            agent.process_autonomy_responses(None)
            if (
                not agent._DIALOGUE_DELIVERY_OUTBOX
                and not agent._DIALOGUE_DELIVERY_RESPONSES
            ):
                break

    with monkeypatch.context() as console_patch:
        console_patch.setattr(agent, "active_sim", lambda _connection: pie_interaction.sim)
        console_patch.setattr(agent, "post_json", console_post)
        console_patch.setattr(agent, "out", lambda _connection, text: console_output.append(text))
        console_patch.setattr(
            agent.threading,
            "Thread",
            lambda target, args=(): SimpleNamespace(
                daemon=False, start=lambda: target(*args)
            ),
        )
        agent.ai_chat("Bob", "|", "Hello", _connection="sync")
        assert agent._DIALOGUE_DELIVERY_OUTBOX[0]["body"]["decision_id"] == (
            "decision-console"
        )
        pump_dialogue_outbox()
        sync_calls = list(console_calls)
        console_response["decision_id"] = "decision-console-async"
        agent.ai_chat_async("Bob", "|", "Hello", _connection="async")
        assert agent._CONSOLE_CHAT_RESPONSES
        pump_dialogue_outbox()
    assert sync_calls[0][1]["available_response_categories"] == list(
        agent.SOCIAL_CATEGORIES
    )
    assert [call[0] for call in sync_calls] == [
        "/chat",
        "/dialogue-result",
        "/dialogue-result",
    ]
    assert console_calls[3][1]["available_response_categories"] == list(
        agent.SOCIAL_CATEGORIES
    )
    assert [call[0] for call in console_calls[3:]] == [
        "/chat",
        "/dialogue-result",
        "/dialogue-result",
    ]
    assert dialogue_attempts == {
        "decision-console": 2,
        "decision-console-async": 2,
    }
    assert any("delivery retrying" in line for line in console_output)
    assert agent._CONSOLE_CHAT_RESPONSES == []
    assert agent._DIALOGUE_DELIVERY_OUTBOX == []

    queued = len(agent._AUTONOMY_RESPONSES)
    with monkeypatch.context() as delivery_patch:
        delivery_patch.setattr(
            agent,
            "post_json",
            lambda _path, payload, timeout=None: {
                "decision_id": payload["decision_id"],
                "status": "already_displayed",
            },
        )
        agent.report_dialogue_delivery(
            pie_interaction.sim,
            player_payload,
            {"decision_id": "decision-already", "animation": "friendly_chat"},
        )
    assert len(agent._AUTONOMY_RESPONSES) == queued

    delivery_calls = []
    with monkeypatch.context() as display_patch:
        display_patch.setattr(
            agent,
            "report_dialogue_delivery",
            lambda *_args: delivery_calls.append(_args),
        )
        unavailable = agent.EmpneonConversationSession(
            pie_interaction, None, pie_interaction.target
        )
        unavailable.phase = "showing_response"
        agent.show_empneon_chat_result(
            unavailable,
            {"decision_id": "decision-not-shown", "dialogue": "No actor."},
            None,
        )
    assert delivery_calls == []

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
    failed_tests.add(incompatible_parent)
    target.potential_interactions = lambda _context: [
        SimpleNamespace(affordance=incompatible_parent)
    ]
    agent.execute_sims_action(
        player_payload,
        {"decision_id": "decision-5", "animation": "friendly_chat"},
        None,
    )
    pump_outbox()
    assert payloads[-1][0] == "/action-result"
    assert payloads[-1][1]["status"] == "failed"
    assert "friendly_chat" in payloads[-1][1]["reason"]
    assert "compatible social super-interaction" in payloads[-1][1]["reason"]
