import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


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
    context_module = ModuleType("interactions.context")
    contexts = []
    context_module.InteractionContext = type(
        "InteractionContext",
        (),
        {
            "SOURCE_AUTONOMY": "autonomy",
            "__init__": lambda self, *args, **kwargs: contexts.append((args, kwargs)),
        },
    )
    context_module.QueueInsertStrategy = SimpleNamespace(LAST="last")
    priority_module = ModuleType("interactions.priority")
    priority_module.Priority = SimpleNamespace(Low="low")
    interactions = ModuleType("interactions")
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
    zone = ModuleType("zone")
    zone.Zone = type("Zone", (), {"on_loading_screen_animation_finished": lambda self: None})
    for name, module in {
        "alarms": alarms,
        "clock": clock,
        "interactions": interactions,
        "interactions.context": context_module,
        "interactions.priority": priority_module,
        "services": services,
        "sims4": sims4,
        "sims4.commands": commands,
        "sims4.resources": resources,
        "zone": zone,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    path = project / "poc" / "ts4script" / "ai_sims_agent.py"
    spec = importlib.util.spec_from_file_location("test_ai_sims_agent", path)
    assert spec and spec.loader
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)

    sims = [SimpleNamespace(sim_id="bella"), SimpleNamespace(sim_id="mortimer")]
    payloads = []
    monkeypatch.setattr(agent, "instanced_npc_infos", lambda: sims)
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

    interaction = SimpleNamespace(finishing_type="FinishingType.NATURAL")
    interaction.register_on_finishing_callback = lambda callback: callback(interaction)
    pushed = []
    actor = SimpleNamespace(
        push_super_affordance=lambda *args: pushed.append(args)
        or SimpleNamespace(interaction=interaction)
    )
    sim_chat = type("sim_Chat", (), {})
    generic_social = type("socials_SuperInteraction", (), {})
    social_mixer_base = type("SocialMixerInteraction", (), {})
    mixer = type(
        "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
        (social_mixer_base,),
        {},
    )
    target = SimpleNamespace()
    infos = {
        "bella": SimpleNamespace(get_sim_instance=lambda: actor),
        "mortimer": SimpleNamespace(get_sim_instance=lambda: target),
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

    assert agent.find_action_affordance("friendly_chat") is sim_chat
    assert agent.social_tuning_names("askaboutday") == [
        "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn"
    ]

    agent.process_autonomy_responses(None)

    assert contexts[0][0][1] == "autonomy"
    assert pushed[0][0:2] == (sim_chat, target)
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
