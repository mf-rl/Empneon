import importlib.util
import io
import struct
import sys
import urllib.error
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


def test_empneon_social_posts_its_conversation_id() -> None:
    source = (Path(__file__).parents[1] / "ts4script" / "ai_sims_agent.py").read_text(
        encoding="utf-8"
    )

    assert 'payload["conversation_id"] = session.id' in source


def test_build_and_installer_use_empneon_artifact_names() -> None:
    root = Path(__file__).parents[1]
    installer = (root / "install_mod.ps1").read_text(encoding="utf-8")
    installer_lines = {line.strip() for line in installer.splitlines()}

    assert build_mod.TARGET.name == "Empneon_TheSims4.ts4script"
    assert build_mod.TUNING_TARGET.name == "Empneon_TheSims4.package"
    assert '"Empneon_TheSims4.ts4script"' in installer
    assert '"Empneon_TheSims4.package"' in installer
    assert '"AI_Sims_Agent.ts4script"' in installer
    assert '"AI_Sims_Agent.package"' in installer
    assert "if (Test-Path $builder) {" in installer_lines
    assert (
        "} elseif (-not ((Test-Path $scriptSource) -and (Test-Path $tuningSource))) {"
        in installer_lines
    )
    assert (
        "if (-not ((Test-Path $scriptSource) -and (Test-Path $tuningSource))) {"
        not in installer_lines
    )


def test_tuning_package_uses_interaction_resource_type() -> None:
    written = []
    target = SimpleNamespace(write_bytes=written.append)
    build_mod.build_tuning_package(build_mod.TUNING_RESOURCES, target)
    package = written[0]
    count, index_offset, index_size = struct.unpack_from("<III", package, 36)
    index_flags = struct.unpack_from("<I", package, index_offset)[0]
    resource_types = [
        struct.unpack_from("<I", package, index_offset + 4 + offset)[0]
        for offset in (0, 32)
    ]

    assert package[:4] == b"DBPF"
    assert (count, index_size, index_flags) == (2, 68, 0)
    assert resource_types == [0xE882D22F, 0xE882D22F]


def test_waiting_tuning_uses_native_social_group_without_loot() -> None:
    tuning = (
        Path(__file__).parents[1] / "tuning" / "empneon_waiting_interaction.xml"
    ).read_text(encoding="utf-8")

    assert '<T n="_social_group_type">16390</T>' in tuning
    assert '<T n="factory">11326</T>' in tuning
    assert tuning.count('<T n="factory">11570</T>') == 2
    assert '<T n="relationship_scoring">False</T>' in tuning
    assert '<V t="loot">' not in tuning


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
    distributor = ModuleType("distributor")
    shared_messages = ModuleType("distributor.shared_messages")
    shared_messages.IconInfoData = lambda **kwargs: SimpleNamespace(**kwargs)
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
    element_utils.build_element = lambda elements: tuple(elements)

    def run_child(_timeline, element):
        yield element

    element_utils.run_child = run_child
    interactions_base = ModuleType("interactions.base")
    super_interaction = ModuleType("interactions.base.super_interaction")
    super_interaction.SuperInteraction = type("SuperInteraction", (), {})
    interactions_social = ModuleType("interactions.social")
    interactions_utils = ModuleType("interactions.utils")
    outcome_utils = ModuleType("interactions.utils.outcome")
    visual_outcomes = []

    def build_outcome_actions(interaction, actions):
        visual_outcomes.append(actions)
        return (
            "visual-outcome",
            actions.animation_ref(interaction, setup_asm_override=None),
        )

    outcome_utils.build_outcome_actions = build_outcome_actions
    social_super_interaction = ModuleType(
        "interactions.social.social_super_interaction"
    )

    class FakeSocialSuperInteraction(super_interaction.SuperInteraction):
        def __init__(
            self,
            *args,
            initiated=True,
            social_group=None,
            source_social_si=None,
            **kwargs,
        ):
            self.initiated = initiated
            self._social_group = social_group or SimpleNamespace(
                on_social_super_interaction_run=lambda: None
            )
            self.source_social_si = source_social_si
            self._saved_participants = {}

        @property
        def social_group(self):
            return self._social_group

        def get_source_social_kwargs(self):
            return {"saved_participants": self._saved_participants}

    social_super_interaction.SocialSuperInteraction = FakeSocialSuperInteraction
    interactions.social = interactions_social
    interactions_social.social_super_interaction = social_super_interaction
    constraints = ModuleType("interactions.constraints")
    constraints.Anywhere = lambda: SimpleNamespace(kind="anywhere")
    constraints.Circle = lambda center, radius, routing_surface=None: SimpleNamespace(
        kind="circle", center=center, radius=radius, routing_surface=routing_surface
    )
    aop_module = ModuleType("interactions.aop")
    context_module = ModuleType("interactions.context")
    interaction_finisher = ModuleType("interactions.interaction_finisher")
    interaction_finisher.FinishingType = SimpleNamespace(
        NATURAL="natural",
        USER_CANCEL="user_cancel",
    )

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
        def __init__(self, affordance, super_interaction=None):
            self.affordance = affordance
            self.super_interaction = super_interaction
            self.outcome = getattr(affordance, "outcome", None)
            self.relationship_scoring = True
            self.finishing_type = ""
            self.finishing_callback = None
            self.canceled = False
            self.basic_elements = []
            self.built_outcomes = []

        def build_outcome(self):
            return ("native-outcome", self.outcome)

        def build_basic_elements(self, sequence):
            self.built_outcomes.append(self.build_outcome())
            self.basic_elements.append(sequence)
            return ("native-social-elements", sequence)

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
            return SimpleNamespace(
                interaction=FakeMappedInteraction(
                    self.affordance,
                    self.super_interaction,
                )
            )

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
        "distributor": distributor,
        "distributor.shared_messages": shared_messages,
        "interactions": interactions,
        "element_utils": element_utils,
        "interactions.base": interactions_base,
        "interactions.base.super_interaction": super_interaction,
        "interactions.social": interactions_social,
        "interactions.social.social_super_interaction": social_super_interaction,
        "interactions.utils": interactions_utils,
        "interactions.utils.outcome": outcome_utils,
        "interactions.constraints": constraints,
        "interactions.aop": aop_module,
        "interactions.context": context_module,
        "interactions.interaction_finisher": interaction_finisher,
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

    usage_output = []
    monkeypatch.setattr(
        agent,
        "active_diagnostic",
        lambda *_args: {
            "requests": 0,
            "by_clod": {},
            "actual": {},
        },
    )
    monkeypatch.setattr(
        agent,
        "query_json",
        lambda path, params: {
            "requests": 2,
            "by_clod": {"2": 1, "3": 1},
            "actual": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "latency_ms": 300,
            },
        },
    )
    monkeypatch.setattr(agent, "out", lambda _connection, text: usage_output.append(text))

    agent.empneon_usage()

    assert usage_output == [
        "Usage: requests=2 CLOD={'2': 1, '3': 1} "
        "prompt=100 completion=20 latency=300ms"
    ]

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
    local_relationship_queries = []
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
            "relationship_payload",
            lambda source, target: local_relationship_queries.append(
                (source, target)
            )
            or {
                "friendship": 7,
                "romance": 12,
                "attraction": 2 / 3,
                "native": {
                    "attraction": {
                        "source": "wickedwhims",
                        "value": 2,
                        "label": "HIGH",
                    }
                },
            },
        )
        command_patch.setattr(
            agent,
            "query_json",
            lambda path, query: relationship_queries.append((path, query))
            or {
                "relationship": {
                    "direction": {"source_id": "cam-id", "target_id": "bella"},
                    "native": {
                        "friendship": 99,
                        "romance": 99,
                        "attraction": {
                            "normalized": -1,
                            "source": "stale",
                            "value": -100,
                            "label": "STALE",
                        },
                    },
                    "empneon": {"trust": 51},
                },
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
    assert local_relationship_queries == [
        (SimpleNamespace(sim_id="cam-id", full_name="Cam Sadya"), rich_info)
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

    pie_affordance = agent.EmpneonSocialInteraction
    waiting_affordance = agent.EmpneonWaitingInteraction
    assert issubclass(waiting_affordance, FakeSocialSuperInteraction)
    services.affordance_manager = lambda: SimpleNamespace(
        get=lambda tuning_id: pie_affordance
        if tuning_id == agent.EMPNEON_SOCIAL_INTERACTION_ID
        else waiting_affordance
        if tuning_id == agent.EMPNEON_WAITING_INTERACTION_ID
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
    queued_waiting = []
    actor = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="alice", full_name="Alice")
    )

    def push_super_affordance(affordance, target, context):
        waiting = affordance()
        waiting.sim = actor
        waiting.target = target
        waiting.context = context
        waiting.affordance = affordance
        waiting.outcome = "neutral-waiting-outcome"
        waiting.listen_animation_calls = []
        waiting.finishing_callback = None
        waiting.register_on_finishing_callback = lambda callback: setattr(
            waiting, "finishing_callback", callback
        )

        def listen_animation(animation_interaction, sequence):
            waiting.listen_animation_calls.append((animation_interaction, sequence))
            return ("listener-animation", sequence)

        waiting.listen_animation = listen_animation
        queued_waiting.append(
            (affordance, target, context, waiting, waiting.get_name())
        )
        return SimpleNamespace(interaction=waiting)

    actor.push_super_affordance = push_super_affordance
    pie_interaction = agent.EmpneonSocialInteraction()
    pie_interaction.sim = actor
    pie_interaction.target = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="bob", full_name="Bob"),
        animation_interaction="listener-animation-interaction",
    )
    runner = pie_interaction._run_interaction_gen("timeline")
    try:
        next(runner)
    except StopIteration as finished:
        assert finished.value is True
    else:
        raise AssertionError("Start conversation stayed in the queue")
    session = agent._CONVERSATION_SESSIONS["alice"]
    assert session.phase == "input"
    assert selected == ["Empneon Social selected: Alice -> Bob"]
    assert agent.EmpneonSocialInteraction.get_name(None, None) == "Empneon Social"
    assert pie_interaction.get_name() == "Start conversation"
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
    submitted_notification = notifications[-1]
    assert submitted_notification.owner is actor
    assert submitted_notification.kwargs["text"]() == "Remember our promise?"
    assert submitted_notification.show_kwargs["icon_override"].obj_instance is actor
    assert (
        submitted_notification.show_kwargs["secondary_icon_override"].obj_instance
        is pie_interaction.target
    )
    assert len(queued_waiting) == 1
    waiting = queued_waiting[0][3]
    assert queued_waiting[0][4] == "Waiting for response"
    assert waiting.get_source_social_kwargs()["empneon_session_id"] == session.id
    assert submitted == [(session, "Remember our promise?")]
    animation_calls = []

    def conversation_animation(interaction, setup_asm_override=None):
        animation_calls.append((interaction, setup_asm_override))
        return "conversation-animation"

    conversation_affordance = SimpleNamespace(
        outcome=SimpleNamespace(
            _fallback_outcomes=(
                SimpleNamespace(
                    outcome=SimpleNamespace(animation_ref=conversation_animation)
                ),
            ),
            decide=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("full native social outcome must not run")
            ),
        )
    )
    waiting_cancellations = []

    def cancel_waiting(finishing_type, cancel_reason_msg=None):
        waiting_cancellations.append((finishing_type, cancel_reason_msg))
        waiting.finishing_callback(waiting)

    waiting.cancel = cancel_waiting
    mapped_aop_count = len(mapped_aops)
    with monkeypatch.context() as acknowledgement_patch:
        acknowledgement_patch.setattr(
            agent,
            "find_action_affordance",
            lambda action: conversation_affordance
            if action == "friendly_chat"
            else None,
        )
        waiting_runner = waiting._run_interaction_gen("timeline")
        assert next(waiting_runner) == (
            (
                "native-social-elements",
                ("visual-outcome", "conversation-animation"),
            ),
            "next-tick",
        )
        animation_owner = animation_calls[0][0]
        assert animation_calls == [(animation_owner, None)]
        assert animation_owner.basic_elements == [
            ("visual-outcome", "conversation-animation")
        ]
        assert animation_owner.outcome is conversation_affordance.outcome
        assert animation_owner.built_outcomes == [()]
        assert animation_owner.relationship_scoring is False
        assert len(visual_outcomes) == 1
        assert visual_outcomes[0].loot_list == ()
        assert visual_outcomes[0].add_target_affordance_loot is False
        assert visual_outcomes[0].continuation is None
        assert visual_outcomes[0].events_to_send == ()
        assert waiting.listen_animation_calls == []
        assert animation_owner is not waiting
        assert animation_owner.affordance is conversation_affordance
        assert animation_owner.super_interaction is waiting
        missing_group_mixer = FakeMappedInteraction(
            conversation_affordance,
            SimpleNamespace(social_group=None),
        )
        unsafe_calls = []

        def unsafe_basic_elements(_sequence):
            unsafe_calls.append(True)
            raise UnboundLocalError(
                "local variable 'listen_animation_factory' "
                "referenced before assignment"
            )

        missing_group_mixer.build_basic_elements = unsafe_basic_elements
        missing_group_waiting = SimpleNamespace(
            _empneon_waiting_mixer=missing_group_mixer,
        )
        marker_count = len(selected)
        expected_fallback = (
            ("visual-outcome", "conversation-animation"),
            "next-tick",
        )
        assert (
            agent.waiting_conversation_animation(
                missing_group_waiting, "next-tick"
            )
            == expected_fallback
        )
        assert (
            agent.waiting_conversation_animation(
                missing_group_waiting, "next-tick"
            )
            == expected_fallback
        )
        assert unsafe_calls == []
        assert (
            missing_group_waiting._empneon_animation_mode
            == "initiator_only"
        )
        assert len(selected) == marker_count + 1
        assert selected[-1].startswith(
            "Waiting conversation animation using initiator-only fallback:"
        )
        animation_call_count = len(animation_calls)
        linked_waiting = agent.EmpneonWaitingInteraction(
            initiated=False,
            empneon_session_id=session.id,
        )
        linked_waiting.sim = pie_interaction.target
        linked_waiting.target = actor
        linked_runner = linked_waiting._run_interaction_gen("timeline")
        assert next(linked_runner) == "next-tick"
        assert len(animation_calls) == animation_call_count
        assert len(queued_waiting) == 1
        assert len(mapped_aops) == mapped_aop_count + 1
        assert animation_owner not in executed
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
        assert waiting_cancellations == [
            ("natural", "Empneon response received")
        ]
        assert len(queued_waiting) == 1
        assert notifications[-1].owner is pie_interaction.target
        assert notifications[-1].kwargs["text"]() == "I remember."
        try:
            next(waiting_runner)
        except StopIteration as finished:
            assert finished.value is True
        else:
            raise AssertionError("Waiting for response stayed queued after the response")
        try:
            next(linked_runner)
        except StopIteration as finished:
            assert finished.value is True
        else:
            raise AssertionError("Linked waiting social stayed queued after the response")
    agent.process_autonomy_responses(None)
    assert session.closed is True
    assert "alice" not in agent._CONVERSATION_SESSIONS

    def fail_animation(_interaction, setup_asm_override=None):
        raise RuntimeError("animation unavailable")

    with monkeypatch.context() as animation_failure_patch:
        animation_failure_patch.setattr(
            agent,
            "find_action_affordance",
            lambda _action: SimpleNamespace(
                outcome=SimpleNamespace(
                    _fallback_outcomes=(
                        SimpleNamespace(
                            outcome=SimpleNamespace(animation_ref=fail_animation)
                        ),
                    )
                )
            ),
        )
        marker_count = len(selected)
        assert agent.waiting_conversation_animation(waiting, "next-tick") == "next-tick"
        assert agent.waiting_conversation_animation(waiting, "next-tick") == "next-tick"
        assert len(selected) == marker_count + 1
        assert selected[-1].startswith("Waiting conversation animation failed:")
        assert waiting._empneon_animation_disabled is True

    runtime_actor = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="animation-runtime", full_name="Alice")
    )
    runtime_target = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="animation-target", full_name="Bob")
    )
    runtime_session = agent.EmpneonConversationSession(
        pie_interaction, runtime_actor, runtime_target
    )
    runtime_session.turn_id = 1
    runtime_session.phase = "waiting_for_backend"
    agent._CONVERSATION_SESSIONS["animation-runtime"] = runtime_session
    runtime_interaction = agent.EmpneonWaitingInteraction()
    runtime_interaction.sim = runtime_actor
    runtime_interaction.target = runtime_target
    runtime_interaction.context = SimpleNamespace(sim=runtime_actor)
    runtime_interaction.affordance = agent.EmpneonWaitingInteraction
    runtime_interaction._empneon_session_id = runtime_session.id
    runtime_session.interaction = runtime_interaction
    runtime_replacements = []

    def push_runtime_waiting(*_args):
        replacement = agent.EmpneonWaitingInteraction()
        replacement._empneon_session_id = runtime_session.id
        replacement.register_on_finishing_callback = lambda callback: setattr(
            replacement, "finishing_callback", callback
        )
        runtime_replacements.append(replacement)
        return SimpleNamespace(interaction=replacement)

    runtime_actor.push_super_affordance = push_runtime_waiting

    def runtime_run_child(_timeline, element):
        if isinstance(element, tuple):
            raise RuntimeError("animation timeline failed")
        yield element

    with monkeypatch.context() as animation_runtime_patch:
        animation_runtime_patch.setattr(
            agent, "find_action_affordance", lambda _action: conversation_affordance
        )
        animation_runtime_patch.setattr(
            agent.element_utils, "run_child", runtime_run_child
        )
        runtime_runner = runtime_interaction._run_interaction_gen("timeline")
        assert next(runtime_runner) == "next-tick"
        assert runtime_session.closed is False
        runtime_runner.close()
    assert runtime_session.closed is False
    assert runtime_session.canceled is False
    assert runtime_session.interaction is runtime_replacements[0]

    def fail_waiting_cancel(*_args, **_kwargs):
        raise RuntimeError("waiting interaction already finished")

    cancel_failure_session = agent.EmpneonConversationSession(
        SimpleNamespace(cancel=fail_waiting_cancel), actor, pie_interaction.target
    )
    cancel_failure_session.turn_id = 1
    cancel_failure_session.phase = "showing_response"
    marker_count = len(selected)
    assert agent.show_empneon_chat_result(
        cancel_failure_session,
        {"dialogue": "The answer still displays.", "suggested_action": "none"},
        None,
    )
    assert cancel_failure_session.response_received is True
    assert len(selected) == marker_count + 2
    assert selected[marker_count].startswith(
        "Waiting interaction completion failed:"
    )

    canceled_actor = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="queue-cancel", full_name="Alice")
    )
    canceled_target = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="bob", full_name="Bob")
    )
    canceled_session = agent.EmpneonConversationSession(
        pie_interaction, canceled_actor, canceled_target
    )
    canceled_session.turn_id = 1
    canceled_session.phase = "waiting_for_backend"
    agent._CONVERSATION_SESSIONS["queue-cancel"] = canceled_session
    canceled_interaction = agent.EmpneonWaitingInteraction()
    canceled_interaction.sim = canceled_actor
    canceled_interaction.target = canceled_target
    canceled_interaction._empneon_session_id = canceled_session.id
    canceled_interaction.finishing_type = agent.FinishingType.USER_CANCEL
    canceled_session.interaction = canceled_interaction
    canceled_runner = canceled_interaction._run_interaction_gen("timeline")
    assert next(canceled_runner) == "next-tick"
    canceled_runner.close()
    assert canceled_session.closed is True
    assert canceled_session.canceled is True
    assert "queue-cancel" not in agent._CONVERSATION_SESSIONS

    race_actor = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="queue-cancel-race", full_name="Alice")
    )
    race_target = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="race-target", full_name="Bob")
    )
    race_interactions = []

    def push_race_waiting(*_args):
        interaction = agent.EmpneonWaitingInteraction()
        interaction.sim = race_actor
        interaction.target = race_target
        interaction.finishing_type = ""
        interaction.finishing_callback = None
        interaction.register_on_finishing_callback = lambda callback: setattr(
            interaction, "finishing_callback", callback
        )
        race_interactions.append(interaction)
        return SimpleNamespace(interaction=interaction)

    race_actor.push_super_affordance = push_race_waiting
    race_session = agent.EmpneonConversationSession(
        pie_interaction, race_actor, race_target
    )
    agent._CONVERSATION_SESSIONS["queue-cancel-race"] = race_session

    submission_count = len(submitted)
    assert agent.queue_awaiting_answer(race_session, "Wait for the reply.")
    assert len(submitted) == submission_count + 1
    assert submitted[-1] == (race_session, "Wait for the reply.")
    first_waiting = race_session.interaction
    first_waiting.finishing_type = "displaced"
    first_waiting.finishing_callback(first_waiting)
    replacement = race_session.interaction
    assert replacement is not first_waiting
    assert replacement._empneon_session_id == race_session.id
    assert race_session.closed is False
    assert len(submitted) == submission_count + 1
    first_waiting.finishing_callback(first_waiting)
    assert race_session.interaction is replacement

    notification_count = len(notifications)
    late = {
        "decision_id": "late-race-decision",
        "dialogue": "This must not be shown.",
        "suggested_action": "none",
    }
    canceled_proposals = []
    replacement.finishing_type = agent.FinishingType.USER_CANCEL
    replacement.finishing_callback(replacement)
    with monkeypatch.context() as race_patch:
        race_patch.setattr(
            agent, "report_canceled_proposal", canceled_proposals.append
        )
        assert race_session.accept_backend_result(1, late, None) is False

    assert race_session.closed is True
    assert race_session.canceled is True
    assert len(notifications) == notification_count
    assert canceled_proposals == [late]

    unavailable_actor = SimpleNamespace(
        sim_info=SimpleNamespace(sim_id="queue-unavailable", full_name="Alice")
    )
    unavailable_session = agent.EmpneonConversationSession(
        pie_interaction, unavailable_actor, None
    )
    unavailable_session.turn_id = 1
    unavailable_session.phase = "waiting_for_backend"
    agent._CONVERSATION_SESSIONS["queue-unavailable"] = unavailable_session
    unavailable_interaction = agent.EmpneonWaitingInteraction()
    unavailable_interaction._empneon_session_id = unavailable_session.id
    unavailable_runner = unavailable_interaction._run_interaction_gen("timeline")
    try:
        next(unavailable_runner)
    except StopIteration as finished:
        assert finished.value is True
    else:
        raise AssertionError("Unavailable participant kept waiting interaction alive")
    assert unavailable_session.closed is True
    assert unavailable_session.canceled is False
    assert "queue-unavailable" not in agent._CONVERSATION_SESSIONS

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
    response_notification = notifications[-1]
    assert response_notification.owner is pie_interaction.target
    assert response_notification.kwargs["title"]() == "Bob"
    assert response_notification.kwargs["text"]() == "I remember."
    assert response_notification.show_kwargs["icon_override"].obj_instance is (
        pie_interaction.target
    )
    assert (
        response_notification.show_kwargs["secondary_icon_override"].obj_instance
        is pie_interaction.sim
    )
    assert len(notifications) == notification_count + 1
    assert delivery_reports == [
        (
            "/dialogue-result",
            {"decision_id": "decision-displayed", "status": "displayed"},
            10,
        )
    ]
    assert agent.show_empneon_notification(
        pie_interaction.sim, "Empneon error", "Provider unavailable"
    )
    assert "secondary_icon_override" not in notifications[-1].show_kwargs
    missing_actor_session = agent.EmpneonConversationSession(
        pie_interaction, None, pie_interaction.target
    )
    assert agent.show_empneon_message_dialog(missing_actor_session) is False
    assert delivery_reports == [
        (
            "/dialogue-result",
            {"decision_id": "decision-displayed", "status": "displayed"},
            10,
        )
    ]
    agent.process_autonomy_responses(None)
    assert display_session.closed is True

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
        "mixer_social_LieAboutCareer_group_mischief_skills", (), {}
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
        "social.mischief": "mixer_social_LieAboutCareer_group_mischief_skills",
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

    action_aop_start = len(mapped_aops)
    agent.process_autonomy_responses(None)

    assert len(mapped_aops) == action_aop_start + 1
    assert mapped_aops[action_aop_start].affordance is mixer
    assert mapped_aops[action_aop_start].target is target
    assert mapped_aops[action_aop_start].push_super_on_prepare is True
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
    assert mapped_aops[action_aop_start + 1].affordance is apologize
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
        "animation": "none",
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
    assert player_session.phase == "showing_response"
    assert len(mapped_aops) == action_aop_start + 2

    delayed_workers.pop(0)()
    assert payloads[3] == (
        "/dialogue-result",
        {"decision_id": "decision-3", "status": "displayed"},
    )
    assert agent._AUTONOMY_RESPONSES == []
    assert len(mapped_aops) == action_aop_start + 2
    monkeypatch.setattr(
        agent.threading,
        "Thread",
        lambda target: SimpleNamespace(daemon=False, start=target),
    )
    agent.process_autonomy_responses(None)
    assert player_session.closed is True
    assert len(mapped_aops) == action_aop_start + 2
    assert callback_order == ["displayed"]

    romance_reports = []
    headline_calls = []
    romance_track.headline = SimpleNamespace(
        send_headline_message=lambda sim_info, value: headline_calls.append(
            (sim_info, value)
        )
    )
    romance_scores = {romance_track: 2}
    response_tracker = SimpleNamespace(
        get_relationship_score=lambda _target, track: romance_scores[track],
        add_relationship_score=lambda _target, amount, track: romance_scores.__setitem__(
            track, romance_scores[track] + amount
        ),
    )
    with monkeypatch.context() as romance_patch:
        romance_patch.setattr(
            agent,
            "post_json",
            lambda path, body, timeout=None: romance_reports.append((path, body)) or body,
        )
        romance_patch.setattr(agent, "find_relationship_track", lambda _name: romance_track)
        romance_session = agent.EmpneonConversationSession(
            pie_interaction,
            SimpleNamespace(sim_info=SimpleNamespace(sim_id="alice")),
            SimpleNamespace(
                sim_info=SimpleNamespace(
                    sim_id="bob", relationship_tracker=response_tracker
                )
            ),
        )
        romance_session.turn_id = 1
        romance_session.phase = "showing_response"
        romance_session.dialogue_acknowledged = True
        romance_session.response_choice_ready = True
        romance_session.response_data = {
            "decision_id": "decision-social-romance",
            "suggested_action": "relationship.romance_positive",
        }
        agent._CONVERSATION_SESSIONS["social-romance"] = romance_session
        action_count = len(mapped_aops)

        assert agent.complete_delivered_turn(romance_session) is True
        assert romance_session.phase == "confirming_relationship"
        assert romance_scores[romance_track] == 7
        assert headline_calls == [
            (romance_session.target.sim_info, 5),
            (romance_session.actor.sim_info, 5),
        ]
        assert len(mapped_aops) == action_count
        assert agent.complete_delivered_turn(romance_session) is False
        assert romance_scores[romance_track] == 7
        headline_calls.clear()
        agent.show_relationship_headlines(
            romance_track,
            romance_session.target.sim_info,
            romance_session.actor.sim_info,
            0,
        )
        assert headline_calls == []

        def fail_headline(_sim_info, _value):
            raise RuntimeError("headline unavailable")

        romance_track.headline = SimpleNamespace(
            send_headline_message=fail_headline
        )
        visual_scores = {romance_track: 10}
        visual_session = agent.EmpneonConversationSession(
            pie_interaction,
            SimpleNamespace(sim_info=SimpleNamespace(sim_id="visual-actor")),
            SimpleNamespace(
                sim_info=SimpleNamespace(
                    sim_id="visual-target",
                    relationship_tracker=SimpleNamespace(
                        get_relationship_score=lambda _target, track: visual_scores[
                            track
                        ],
                        add_relationship_score=lambda _target, amount, track: (
                            visual_scores.__setitem__(
                                track, visual_scores[track] + amount
                            )
                        ),
                    ),
                )
            ),
        )
        marker_count = len(selected)
        changes, error = agent.apply_relationship_outcome(
            visual_session, "relationship.romance_positive"
        )
        assert error is None
        assert changes == [
            {
                "path": "relationship.romance",
                "operation": "increment",
                "value": 5,
            }
        ]
        assert len(selected) == marker_count + 2
        assert all(
            marker.startswith("Relationship headline failed:")
            for marker in selected[marker_count:]
        )
        pump_outbox()
        agent.process_autonomy_responses(None)

    assert romance_reports[-1] == (
        "/action-result",
        {
            "decision_id": "decision-social-romance",
            "action": "relationship.romance_positive",
            "status": "succeeded",
                "reason": None,
                "changes": [
                    {
                        "path": "relationship.romance",
                        "operation": "increment",
                        "value": 5,
                    }
                ],
        },
    )
    assert romance_session.closed is True

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
    assert native_interaction.canceled is False
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
    assert lost_ack_session.closed is True
    assert lost_ack_session.canceled is False
    assert lost_ack_session.phase == "closed"
    assert lost_ack_submitted == []

    retry_session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    retry_session.turn_id = 1
    retry_session.phase = "waiting_for_backend"
    dialog_count = len(dialogs)
    retry_session.accept_backend_result(1, None, "provider unavailable")
    assert retry_session.closed is True
    assert retry_session.phase == "closed"
    assert len(dialogs) == dialog_count

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
    assert failed_post_session.closed is True

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

    permanent_attempts = []

    def permanently_rejected_post(_path, body, timeout=None):
        permanent_attempts.append(body["decision_id"])
        raise urllib.error.HTTPError(
            "/action-result",
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"error":"unknown or conflicting action proposal"}'),
        )

    monkeypatch.setattr(agent, "post_json", permanently_rejected_post)
    agent.report_action_result(
        "decision-permanent",
        "friendly_chat",
        "failed",
        "interaction canceled",
    )
    permanent_item = agent._ACTION_RESULT_OUTBOX[-1]
    pump_outbox()

    assert permanent_attempts == ["decision-permanent"]
    assert permanent_item["paused"] is True
    assert permanent_item["attempts"] == 1
    assert any(
        "decision-permanent" in marker
        and "HTTP 400" in marker
        and "unknown or conflicting action proposal" in marker
        for marker in selected
    )
    agent._ACTION_RESULT_OUTBOX.remove(permanent_item)

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
