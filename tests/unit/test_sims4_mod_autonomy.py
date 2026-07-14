import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from poc import build_mod


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
    project = Path(__file__).parents[2]
    monkeypatch.setenv("HOME", str(project / "tests"))
    monkeypatch.setenv("USERPROFILE", str(project / "tests"))
    alarms = ModuleType("alarms")
    alarms.cancel_alarm = lambda _handle: None
    alarms.add_alarm = lambda *_args, **_kwargs: object()
    clock = ModuleType("clock")
    clock.interval_in_sim_minutes = lambda minutes: minutes
    services = ModuleType("services")
    interactions = ModuleType("interactions")
    interactions_base = ModuleType("interactions.base")
    immediate_interaction = ModuleType("interactions.base.immediate_interaction")
    immediate_interaction.ImmediateSuperInteraction = type(
        "ImmediateSuperInteraction", (), {}
    )
    aop_module = ModuleType("interactions.aop")
    executed = []
    aop_module.AffordanceObjectPair = SimpleNamespace(
        execute_interaction=lambda interaction: executed.append(interaction) or True
    )
    commands = ModuleType("sims4.commands")
    commands.CommandType = SimpleNamespace(Live="live")
    commands.Command = lambda *_args, **_kwargs: lambda function: function
    commands.CheatOutput = lambda _connection: lambda _text: None
    sims4 = ModuleType("sims4")
    sims4.commands = commands
    resources = ModuleType("sims4.resources")
    resources.Types = SimpleNamespace(INTERACTION="interaction")
    resources.get_resource_key = lambda name, resource_type: (name, resource_type)
    sims4.resources = resources
    localization = ModuleType("sims4.localization")
    localization.LocalizationHelperTuning = SimpleNamespace(get_raw_text=lambda text: text)
    sims = ModuleType("sims")
    sim_module = ModuleType("sims.sim")
    sim_module.Sim = type("Sim", (), {"on_add": lambda self: "added"})
    zone = ModuleType("zone")
    zone.Zone = type("Zone", (), {"on_loading_screen_animation_finished": lambda self: None})
    for name, module in {
        "alarms": alarms,
        "clock": clock,
        "interactions": interactions,
        "interactions.base": interactions_base,
        "interactions.base.immediate_interaction": immediate_interaction,
        "interactions.aop": aop_module,
        "services": services,
        "sims": sims,
        "sims.sim": sim_module,
        "sims4": sims4,
        "sims4.commands": commands,
        "sims4.localization": localization,
        "sims4.resources": resources,
        "zone": zone,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    path = project / "poc" / "ts4script" / "ai_sims_agent.py"
    spec = importlib.util.spec_from_file_location("test_ai_sims_agent", path)
    assert spec and spec.loader
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)

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
    pie_interaction = agent.EmpneonSocialInteraction()
    pie_interaction.sim = SimpleNamespace(sim_info=SimpleNamespace(full_name="Alice"))
    pie_interaction.target = SimpleNamespace(sim_info=SimpleNamespace(full_name="Bob"))
    try:
        next(pie_interaction._run_interaction_gen(None))
    except StopIteration as finished:
        assert finished.value is True
    assert selected == ["Empneon Social selected: Alice -> Bob"]
    assert agent.EmpneonSocialInteraction.get_name(None, None) == "Empneon Social"

    sim_chat = type("native_NPC_social", (), {})
    target = type(
        "Target",
        (),
        {"commodity_flags": frozenset(("social",)), "is_selectable": False},
    )()
    interaction = SimpleNamespace(
        affordance=sim_chat,
        finishing_type="FinishingType.NATURAL",
        target=target,
    )
    interaction.register_on_finishing_callback = lambda callback: callback(interaction)
    request = SimpleNamespace(object_list=None)
    actor = SimpleNamespace(
        autonomy_component=SimpleNamespace(_create_autonomy_request=lambda: request)
    )
    bella = SimpleNamespace(sim_id="bella", get_sim_instance=lambda: actor)
    mortimer = SimpleNamespace(sim_id="mortimer", get_sim_instance=lambda: target)
    target.sim_info = mortimer
    sims = [bella, mortimer]
    payloads = []
    monkeypatch.setattr(agent, "instanced_npc_infos", lambda: sims)

    def find_best_action(selected_request):
        motives = ("social",)
        if selected_request.object_list:
            for candidate in selected_request.object_list:
                candidate.commodity_flags & motives
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

    generic_social = type("socials_SuperInteraction", (), {})
    social_mixer_base = type("SocialMixerInteraction", (), {})
    mixer = type(
        "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
        (social_mixer_base,),
        {},
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
            2: generic_social,
            3: custom_social,
            4: mixer,
            5: sim_chat,
        },
    )
    monkeypatch.setattr(
        agent.services, "get_instance_manager", lambda _type: manager, raising=False
    )

    assert agent.find_action_affordance("friendly_chat") is mixer
    assert agent.social_tuning_names("askaboutday") == [
        "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn"
    ]

    agent.process_autonomy_responses(None)

    assert executed == [interaction]
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
