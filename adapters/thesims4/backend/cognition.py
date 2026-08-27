# ruff: noqa: E501

import ast
import dataclasses
import json
import re
from collections import Counter
from difflib import SequenceMatcher

from empneon.core.contracts import SOCIAL_CATEGORIES
from empneon.core.memory.recall import (
    analyze_recall_query,
    fact_supports_query,
    validate_recall_response,
)
from empneon.providers.llm import ProviderError

from backend import empneon_state
from empneon_thesims4 import Sims4Adapter

UNKNOWN_SIM_NAME = "Unknown Sim"
UNKNOWN_ACTOR_NAME = "Unknown actor"


def sim_name(sim):
    return str(sim.get("name") or sim.get("id") or UNKNOWN_SIM_NAME)


def dumps(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


SYSTEM_PROMPT = """You roleplay one The Sims 4 character.
Stay grounded in the Sim profile, relationship, current mood, and recalled history.
Return one valid JSON object only. No markdown. No schema explanation. No placeholders.
Do not write a thinking process, analysis, reasoning, or chain-of-thought.
The first character of your response must be {.
Normally write 2 to 4 natural sentences totaling about 25 to 60 words. Use a shorter answer only
when the situation genuinely calls for one. Make the dialogue reflect the Sim's personality,
emotion, and relationship instead of using generic filler.
Never invent a past event, shared fact, codeword, promise, plan, date, or name. For factual recall,
use only the attributed statements and confirmed exchanges supplied in the request. If the
requested fact is absent, say naturally and in character that the Sim does not know or remember it.
Use this exact shape with concrete values:
{
  "dialogue": "expressive in-character reply",
  "expressed_emotion": "playful",
  "intent": "accept_playfully",
  "response_category": "romance",
  "tone_tags": ["playful", "hesitant"],
  "trust_delta": 1,
  "relationship_outcome": "romance_positive"
}

Choose one response category from the request's available common social categories. The response
category describes the Speaker's own dialogue, independently from the incoming category. Tone tags
may blend style and mood, but never select additional actions. Choose friendship_positive only for
a warm or funny response, friendship_negative only for a mean or hostile response,
romance_positive only when the Speaker clearly reciprocates romance, romance_negative only for an
explicit romantic rejection, and none otherwise. Do not return numeric friendship, romance,
attraction, tuning, or action fields; the adapter and game own them.
"""

SOCIAL_ACTIONS = {category: "social." + category for category in SOCIAL_CATEGORIES}
RELATIONSHIP_OUTCOMES = (
    "friendship_positive",
    "friendship_negative",
    "romance_positive",
    "romance_negative",
    "none",
)
ROMANTIC_RECIPROCATION = re.compile(
    r"\b(yes|i would love|i'd love|me too|feel the same|date sounds|be together)\b"
)
ROMANTIC_REJECTION = re.compile(
    r"\b(no|not interested|rather stay friends|do not want|don't want|cannot|can't)\b"
)

DIALOGUE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "dialogue": {"type": "string"},
        "expressed_emotion": {"type": "string"},
        "intent": {"type": "string"},
        "response_category": {
            "type": "string",
            "enum": list(SOCIAL_CATEGORIES),
        },
        "tone_tags": {
            "type": "array",
            "items": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,31}$"},
            "maxItems": 3,
            "uniqueItems": True,
        },
        "trust_delta": {"type": "integer", "minimum": -10, "maximum": 10},
        "relationship_outcome": {
            "type": "string",
            "enum": list(RELATIONSHIP_OUTCOMES),
        },
    },
    "required": [
        "dialogue",
        "expressed_emotion",
        "intent",
        "response_category",
        "tone_tags",
        "trust_delta",
        "relationship_outcome",
    ],
}

MEMORY_SELECTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "event_ids": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 3,
        }
    },
    "required": ["event_ids"],
}


def available_actions(value):
    return tuple(
        dict.fromkeys(
            str(action)
            for action in (value if isinstance(value, (list, tuple)) else ())
            if str(action) in ("friendly_chat", "apologize", "flirt")
        )
    )


def available_response_categories(value):
    return tuple(
        dict.fromkeys(
            str(category)
            for category in (value if isinstance(value, (list, tuple)) else ())
            if str(category) in SOCIAL_CATEGORIES
        )
    )


def dialogue_schema(value):
    schema = json.loads(json.dumps(DIALOGUE_SCHEMA))
    categories = available_response_categories(value) or SOCIAL_CATEGORIES
    schema["properties"]["response_category"] = {
        "type": "string",
        "enum": list(categories),
    }
    return schema


DIRECTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "hook": {"type": "string"},
        "target": {"type": "string"},
        "suggested_action": {"type": "string"},
        "tone": {"type": "string"},
    },
    "required": ["hook", "target", "suggested_action", "tone"],
}


def clamp_int(value, low=-10, high=10):
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        value = 0
    return max(low, min(high, value))


def clamp_float(value, low=0.0, high=1.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.5
    return max(low, min(high, value))


def sanitize_action_proposal(response, actions):
    allowed = set(available_actions(actions))
    action = str(response.get("suggested_action") or "none")
    if action not in allowed:
        action = "none"
    dialogue = str(response.get("dialogue") or "").casefold()
    if action == "flirt" and re.search(
        r"\bno\b|not interested|rather stay friends|do not want|don't want",
        dialogue,
    ):
        action = "none"
    response["suggested_action"] = action
    return response


def _is_warm_romance(category, tone_tags, dialogue):
    return (
        category == "romance"
        and bool(tone_tags & {"warm", "playful", "romantic"})
        and not tone_tags & {"hesitant", "neutral", "uncertain", "hostile"}
        and not ROMANTIC_REJECTION.search(dialogue)
    )


def _relationship_outcome_rejected(value, category, dialogue, warm_romance):
    if value == "friendship_positive" and category not in ("friendly", "funny"):
        return True
    if value == "friendship_negative" and category not in ("mean", "mischief"):
        return True
    if value == "romance_positive" and (
        category != "romance" or not (ROMANTIC_RECIPROCATION.search(dialogue) or warm_romance)
    ):
        return True
    if value == "romance_negative" and (
        category != "romance" or not ROMANTIC_REJECTION.search(dialogue)
    ):
        return True
    return False


def validated_relationship_outcome(response):
    value = str(response.get("relationship_outcome") or "none")
    dialogue = str(response.get("dialogue") or "").casefold()
    category = str(response.get("response_category") or "")
    tone_tags = {str(tag).strip().casefold() for tag in response.get("tone_tags") or ()}
    warm_romance = _is_warm_romance(category, tone_tags, dialogue)
    if value not in RELATIONSHIP_OUTCOMES:
        return "none"
    if _relationship_outcome_rejected(value, category, dialogue, warm_romance):
        return "none"
    if value == "none" and warm_romance:
        return "romance_positive"
    return value


def _normalized_category(raw, available_categories):
    categories = (
        available_response_categories(available_categories)
        if available_categories is not None
        else SOCIAL_CATEGORIES
    )
    legacy_categories = {
        "friendly": "friendly",
        "friendship": "friendly",
        "romantic_compliment": "romance",
        "romantic_invitation": "romance",
        "hostile": "mean",
        "informational": "friendly",
        "neutral": "friendly",
    }
    legacy_kind = str(raw.get("player_interaction_kind") or "")
    raw_category = str(raw.get("response_category") or legacy_kind or "friendly")
    category = legacy_categories.get(raw_category, raw_category)
    if category not in categories:
        raise ValueError("response_category is invalid or unavailable")
    return category


def _validated_tone_tags(raw):
    tone_tags = raw.get("tone_tags") or []
    if (
        not isinstance(tone_tags, list)
        or len(tone_tags) > 3
        or len(set(tone_tags)) != len(tone_tags)
        or any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", str(tag)) for tag in tone_tags)
    ):
        raise ValueError("tone_tags are invalid")
    return tone_tags


def _normalized_memory(raw):
    memory = raw.get("memory")
    if isinstance(memory, str):
        memory = {"summary": memory, "importance": 0.5}
    elif not isinstance(memory, dict):
        memory = {}
    return memory


def normalize_response(raw, available_categories=None):
    if not isinstance(raw, dict):
        raw = {}

    category = _normalized_category(raw, available_categories)
    tone_tags = _validated_tone_tags(raw)
    memory = _normalized_memory(raw)

    dialogue = str(raw.get("dialogue") or "").strip() or "..."
    expressed_emotion = (
        str(raw.get("expressed_emotion") or raw.get("emotion") or "neutral").strip().lower()
    )
    relationship = raw.get("relationship")
    relationship = relationship if isinstance(relationship, dict) else {}
    trust = raw.get("trust_delta")
    if trust is None:
        trust = relationship.get("trust_delta")
    response = {
        "dialogue": dialogue,
        "expressed_emotion": expressed_emotion,
        "emotion": expressed_emotion,
        "intent": str(raw.get("intent") or "respond").strip(),
        "response_category": category,
        "tone_tags": [str(tag) for tag in tone_tags],
        "trust_delta": clamp_int(trust),
        "memory": {
            "importance": clamp_float(memory.get("importance")),
            "summary": str(memory.get("summary") or "").strip(),
        },
        "suggested_action": SOCIAL_ACTIONS[category],
        "animation": SOCIAL_ACTIONS[category],
    }
    response["relationship_outcome"] = validated_relationship_outcome(
        dict(response, relationship_outcome=raw.get("relationship_outcome"))
    )
    return response


def _strip_code_fence(text):
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _decode_json_object_at(text):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def extract_json(text):
    text = str(text or "").strip()
    text = _strip_code_fence(text)

    parsed = _decode_json_object_at(text)
    if parsed is not None:
        return parsed

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("model did not return a JSON object")
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    try:
        parsed = ast.literal_eval(candidate)
        if isinstance(parsed, dict):
            return parsed
    except (SyntaxError, ValueError):
        pass
    # ponytail: handles common local-model JSON-ish output; replace with
    # schema-constrained decoding if needed.
    quoted_keys = re.sub(r"([{,]\s*)([A-Za-z_]\w*)(\s*:)", r'\1"\2"\3', candidate)
    return json.loads(quoted_keys)


def fallback_response(text, available_categories=None):
    dialogue = str(text or "").strip()
    if not dialogue or any(marker in dialogue for marker in ("{", "}", "```")):
        dialogue = "I couldn't form a reliable response. Please try again."
    categories = (
        available_response_categories(available_categories)
        if available_categories is not None
        else SOCIAL_CATEGORIES
    )
    category = classify_social_category(dialogue)
    if category not in categories:
        category = "friendly" if "friendly" in categories else categories[0]
    response = normalize_response(
        {
            "dialogue": dialogue,
            "emotion": "neutral",
            "intent": "respond",
            "response_category": category,
            "relationship_outcome": ("friendship_negative" if category == "mean" else "none"),
            "memory": {"importance": 0.0, "summary": ""},
        },
        categories,
    )
    response["suggested_action"] = response["animation"] = "none"
    return response


_FULL_EXCHANGE_QUERY = re.compile(
    r"\b(?:what (?:did (?:we|you|i) (?:say|discuss|talk about)|was said)"
    r"|how did\b|how was (?:our|the) (?:conversation|interaction))",
    re.IGNORECASE,
)


def _facts_filtered_candidates(query, candidates):
    if any(candidate.get("facts") for candidate in candidates) and not (
        _FULL_EXCHANGE_QUERY.search(str(query or ""))
    ):
        return [candidate for candidate in candidates if candidate.get("facts")]
    return candidates


def _memory_selector_blocks(aliased):
    blocks = []
    for memory_id, candidate in aliased:
        facts = " | ".join(
            "{}: {}".format(
                fact.get("actor_id") or "unknown",
                fact.get("statement") or "",
            )
            for fact in candidate.get("facts") or []
            if isinstance(fact, dict)
        )
        blocks.append(
            "MEMORY {event_id}\nFACTS: {facts}\nPLAYER: {message}\nSIM: {dialogue}".format(
                event_id=memory_id,
                facts=facts or "none",
                message=candidate.get("message") or "",
                dialogue=candidate.get("dialogue") or "",
            )
        )
    return blocks


def _memory_selector_prompt(query, blocks):
    return """Current message:
{query}

Candidate memories:
{candidates}

Select zero to three event_ids that provide evidence relevant to the current message.
Match meaning, not exact wording.
Prefer attributed facts for plans, preferences, promises, identity, locations, and past events.
Use full exchanges only when the player asks what was said or how an interaction occurred.
A previous answer to a memory question without supporting facts is not authoritative evidence.
Related conversation that does not contain the requested answer is not evidence.
Return exactly {{"event_ids":[]}} when no memory is relevant.
""".format(
        query=str(query),
        candidates="\n\n".join(blocks),
    )


def _validated_selector_event_ids(raw, by_id):
    event_ids = raw.get("event_ids")
    if not isinstance(event_ids, list) or len(event_ids) > 3:
        return None
    if any(not isinstance(event_id, str) for event_id in event_ids):
        return None
    if len(set(event_ids)) != len(event_ids):
        return None
    if any(event_id not in by_id for event_id in event_ids):
        return None
    return event_ids


def _finalized_selected_memories(selected):
    grounded = [item for item in selected if item.get("facts")]
    if grounded:
        selected = grounded
    result = [dict(item, explicit=True) for item in selected]
    if result and result[0].get("facts"):
        result[0]["semantic_primary"] = True
    return result


def select_recalled_memories(query, candidates, generate):
    candidates = _facts_filtered_candidates(query, candidates)
    aliased = [
        (f"m{index}", candidate) for index, candidate in enumerate(candidates, start=1)
    ]
    blocks = _memory_selector_blocks(aliased)
    prompt = _memory_selector_prompt(query, blocks)
    content = generate(
        [
            {
                "role": "system",
                "content": (
                    "Select relevant Sims memories. "
                    'Return exactly {"event_ids":["<memory_id>"]} with up to three '
                    "candidate IDs, or an empty event_ids list. No prose."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        schema=MEMORY_SELECTOR_SCHEMA,
        schema_name="sims_memory_selector",
        task="small",
    )
    try:
        raw = extract_json(content)
    except ValueError:
        return []
    by_id = dict(aliased)
    event_ids = _validated_selector_event_ids(raw, by_id)
    if event_ids is None:
        return []
    selected = [by_id[event_id] for event_id in event_ids]
    return _finalized_selected_memories(selected)


def semantic_recalled_memories(query, candidates, fallback, select_memories, log_warning):
    if not candidates:
        return fallback
    try:
        selected = select_memories(query, candidates)
    except (ProviderError, ValueError, OSError):
        log_warning("semantic memory selection failed; using deterministic recall")
        return fallback
    if any(item.get("facts") for item in fallback) and not any(
        item.get("facts") for item in selected
    ):
        return fallback
    return selected or fallback


def _actor_snapshot(payload, role):
    other = "listener" if role == "speaker" else "speaker"
    actor_payload = dict(payload)
    actor_payload.pop("sim", None)
    actor_payload["speaker"] = payload.get(role) or {}
    actor_payload["listener"] = payload.get(other) or {}
    actor_payload["relationship"] = (
        payload.get("relationship") if role == "speaker" else payload.get("listener_relationship")
    ) or {}
    return dataclasses.asdict(Sims4Adapter(actor_payload).agent_state())


def _entity_traits(identity, entity, profile):
    if isinstance(identity, dict) and "traits" in identity:
        return identity.get("traits") or []
    return entity.get("traits") or profile.get("identity", {}).get("traits") or []


def _speaker_game_state(speaker):
    return {
        "needs": speaker.get("needs") or {},
        "moodlets": speaker.get("moodlets") or [],
        "aspiration": speaker.get("aspiration") or "unknown",
        "career": speaker.get("career") or "unknown",
        "skills": speaker.get("skills") or {},
        "household": speaker.get("household") or {},
    }


def build_context(
    payload,
    speaker_profile,
    listener_profile,
    relationship,
    emotions,
    recalled_memories,
):
    speaker = payload.get("speaker") or {}
    listener = payload.get("listener") or {}
    speaker_identity = speaker.get("identity") or {}
    listener_identity = listener.get("identity") or {}
    speaker_state = _actor_snapshot(payload, "speaker")
    listener_state = _actor_snapshot(payload, "listener")
    return {
        "speaker": speaker_profile,
        "listener": listener_profile,
        "relationship": relationship,
        "emotions": emotions,
        "recalled_memories": recalled_memories,
        "location": payload.get("location") or "unknown",
        "nearby_sims": payload.get("nearby_sims") or [],
        "message": payload.get("message") or "",
        "speaker_identity": speaker_identity,
        "listener_identity": listener_identity,
        "speaker_state": speaker_state,
        "listener_state": listener_state,
        "speaker_traits": _entity_traits(speaker_identity, speaker, speaker_profile),
        "listener_traits": _entity_traits(listener_identity, listener, listener_profile),
        "game_state": _speaker_game_state(speaker),
    }


def _exchange_text(turns, context, *, limit, max_chars):
    speaker_name = context["speaker"].get("name") or UNKNOWN_SIM_NAME
    listener_name = context["listener"].get("name") or UNKNOWN_SIM_NAME
    blocks = []
    for turn in list(turns or [])[-limit:]:
        if turn.get("speaker_id") == context.get("speaker_id"):
            asker, respondent = listener_name, speaker_name
        else:
            asker, respondent = speaker_name, listener_name
        blocks.append(
            "{}: {}\n{}: {}".format(
                asker,
                turn.get("message") or "",
                respondent,
                turn.get("dialogue") or "",
            )
        )
    selected = []
    used = 0
    for block in reversed(blocks):
        cost = len(block) + 1
        if used + cost > max_chars:
            break
        selected.append(block)
        used += cost
    return "\n".join(reversed(selected)) or "None yet"


def _explicit_memory_line(memory, context, names):
    if not memory.get("explicit"):
        return None
    asker_id = (
        context.get("listener_id")
        if memory.get("speaker_id") == context.get("speaker_id")
        else context.get("speaker_id")
    )
    message = str(memory.get("message") or "").strip()
    if not message:
        return None
    return f"{names.get(asker_id, asker_id)} said: {message}"


def _memory_fact_lines(memory, names):
    lines = []
    for fact in memory.get("facts") or []:
        actor_id = str(fact.get("actor_id") or "")
        statement = str(fact.get("statement") or "").strip()
        if statement:
            lines.append(f"{names.get(actor_id, actor_id)} said: {statement}")
    return lines


def _recalled_memory_text(context):
    names = {
        context.get("speaker_id"): context["speaker"].get("name") or UNKNOWN_SIM_NAME,
        context.get("listener_id"): context["listener"].get("name") or UNKNOWN_SIM_NAME,
    }
    lines = []
    for memory in list(context.get("recalled_memories") or [])[-3:]:
        explicit_line = _explicit_memory_line(memory, context, names)
        if explicit_line:
            lines.append(explicit_line)
        lines.extend(_memory_fact_lines(memory, names))
    return "\n".join(lines) or "None yet"


def _nearby_sims_text(nearby_sims):
    return (
        ", ".join(
            sim_name(item) if isinstance(item, dict) else str(item) for item in nearby_sims
        )
        or "none"
    )


def _traits_text(traits):
    return (
        ", ".join(
            str(item.get("label") or item.get("id") or "unknown")
            if isinstance(item, dict)
            else str(item)
            for item in traits
        )
        or "unknown"
    )


def _prompt_response_categories(payload):
    if payload.get("available_response_categories") is None:
        return SOCIAL_CATEGORIES
    return available_response_categories(payload.get("available_response_categories"))


def _chat_prompt_speaker_fields(speaker_profile, game_state, goals, speaker_traits, household_name, context):
    return {
        "speaker_name": speaker_profile.get("name") or UNKNOWN_SIM_NAME,
        "speaker_identity": dumps(context["speaker_identity"]),
        "speaker_traits": speaker_traits,
        "personality": dumps(speaker_profile.get("personality") or {}),
        "values": ", ".join(speaker_profile.get("values") or []) or "unknown",
        "rules": ", ".join(speaker_profile.get("behavioral_rules") or []) or "none",
        "knowledge": dumps(speaker_profile.get("knowledge") or {}),
        "goals": ", ".join(str(goal) for goal in goals) or "none",
        "needs": dumps(game_state["needs"]),
        "moodlets": ", ".join(str(item) for item in game_state["moodlets"]) or "none",
        "aspiration": game_state["aspiration"],
        "career": game_state["career"],
        "skills": dumps(game_state["skills"]),
        "household": household_name or "unknown",
        "speaker_state": dumps(context["speaker_state"]),
    }


def _chat_prompt_listener_fields(listener_profile, listener_traits, context):
    return {
        "listener_name": listener_profile.get("name") or UNKNOWN_SIM_NAME,
        "listener_identity": dumps(context["listener_identity"]),
        "listener_traits": listener_traits,
        "listener_state": dumps(context["listener_state"]),
    }


def _chat_prompt_scene_fields(
    payload, context, relationship, emotions, recalled_history, nearby, conversation_marker, categories
):
    return {
        "relationship": dumps(relationship),
        "emotions": dumps(emotions),
        "recent_conversation": conversation_marker,
        "recalled_history": recalled_history,
        "location": context["location"],
        "nearby": nearby,
        "incoming_category": payload.get("incoming_category") or "friendly",
        "available_response_categories": ", ".join(categories) or "none",
        "message": payload.get("message") or "",
    }


def build_chat_prompt(payload, context):
    speaker_profile = context["speaker"]
    listener_profile = context["listener"]
    relationship = context["relationship"]
    emotions = context["emotions"]
    recalled_history = _recalled_memory_text(context)
    nearby = _nearby_sims_text(context["nearby_sims"])
    game_state = context["game_state"]
    household = game_state["household"]
    household_name = household.get("name") if isinstance(household, dict) else household
    goals = speaker_profile.get("goals") or []
    speaker_traits = _traits_text(context["speaker_traits"])
    listener_traits = _traits_text(context["listener_traits"])
    conversation_marker = "__EMPNEON_CURRENT_SOCIAL__"
    categories = _prompt_response_categories(payload)

    prompt = """Role assignment:
You are {speaker_name}, the Speaker.
{listener_name} is the Listener and wrote the message below.
Reply as {speaker_name} to {listener_name}.
Never address the Listener by the Speaker's name.
Do not include the Speaker's name in dialogue.

Speaker:
{speaker_name}
Speaker identity: {speaker_identity}
Traits: {speaker_traits}
Personality: {personality}
Values: {values}
Behavior rules: {rules}
Knowledge: {knowledge}
Goals: {goals}
Needs: {needs}
Moodlets: {moodlets}
Aspiration: {aspiration}
Career: {career}
Skills: {skills}
Household: {household}

Listener:
{listener_name}
Listener identity: {listener_identity}
Traits: {listener_traits}

Speaker current state:
{speaker_state}

Listener current state:
{listener_state}

Relationship:
{relationship}

Current emotion:
{emotions}

Recalled long-term history:
{recalled_history}

Location:
{location}

Nearby Sims:
{nearby}

Incoming social category: {incoming_category}
Available response categories: {available_response_categories}
Choose the Speaker's response category independently from the incoming category.
Use exactly one primary response category. Tone tags may blend style, mood, and personality but do
not select additional actions.
The Speaker may accept, reject, joke, retaliate, or deflect according to both actor states.
Do not return friendship, romance, attraction, or action fields; the adapter and game own them.

Current Empneon Social:
{recent_conversation}

Grounding rules:
- Answer the current message without restating or closely paraphrasing it.
- Keep the reply distinct from every recent player input and Speaker reply.
- Advance the conversation with a new reaction, detail, question, or decision instead of reusing
  an earlier opening or sentence frame.
- Use the Speaker's traits to shape tone, preferences, confidence, boundaries, and choices.
- Combine traits with current mood, needs, relationship, recalled history, and the current message.
- Do not merely name or caricature traits.
- Relationship attraction, when present, is the Speaker's attraction toward the Listener:
  -1 is strong aversion, 0 is neutral, and 1 is strong attraction.
- Attraction may shape warmth, hesitation, boundaries, or romantic openness, but
  it does not imply consent or require flirtation and never overrides identity, mood, memory, history, or the message.
- A close or romantic relationship and compatible traits may inspire a fresh, natural term of
  endearment, but never require one.
- Do not use a term of endearment for neutral or hostile relationships, rejected romance, or when
  identity or context makes it inappropriate.
- Use gendered relationship terms only when supported by supplied identity.
- Do not guess gender or age when identity is unknown.
- A fact about shared history is supported only when it appears in Recalled long-term history or
  something the Listener said in the current Empneon Social.
- Treat every recalled statement as attributed to the Sim whose name prefixes it; do not transfer
  one actor's traits, preferences, promises, or identity to the other actor.
- The Speaker's earlier generated replies in the current Empneon Social provide conversational
  tone, but are not evidence that a fact is true.
- When asked for an unsupported fact, do not guess. Say naturally that you do not know or do not
  remember.
- When the Listener supplies or corrects a concrete fact, use its exact value.
- When asked about a supported plan or agreement, answer with the exact activity, date, and time
  available in the evidence.
- Needs are context, not required topics. A satisfied need is normally silent; a low need may
  motivate a gentle suggestion; a critical need should strongly influence urgency and may redirect
  the conversation, but the Speaker may still continue the current topic.
- Express needs naturally in-world. Do not recite need names, status labels, or numeric values.

Player says:
{message}
""".format(
        **_chat_prompt_speaker_fields(
            speaker_profile, game_state, goals, speaker_traits, household_name, context
        ),
        **_chat_prompt_listener_fields(listener_profile, listener_traits, context),
        **_chat_prompt_scene_fields(
            payload,
            context,
            relationship,
            emotions,
            recalled_history,
            nearby,
            conversation_marker,
            categories,
        ),
    )
    prompt_chars = max(
        0,
        (
            int(context.get("max_context_tokens") or 4096)
            - int(context.get("max_completion_tokens") or 350)
        )
        * 3
        - len(prompt)
        + len(conversation_marker),
    )
    recent_conversation = _exchange_text(
        context.get("conversation"),
        context,
        limit=6,
        max_chars=min(6000, prompt_chars),
    )
    return prompt.replace(conversation_marker, recent_conversation)


def _identity_gender(identity):
    value = identity.get("gender") if isinstance(identity, dict) else identity
    if isinstance(value, dict):
        value = value.get("key") or value.get("value") or value.get("label")
    tokens = set(re.findall(r"[a-z]+", str(value or "").casefold()))
    if tokens & {"female", "woman", "girl"}:
        return "female"
    if tokens & {"male", "man", "boy"}:
        return "male"
    return "unknown"


def _mask_quoted_dialogue(dialogue):
    masked = re.sub(
        r'"[^"]*"|“[^”]*”|‘[^’]*’',
        " ",
        str(dialogue or "").casefold(),
    )
    characters = list(masked)
    opening = None
    for index, character in enumerate(characters):
        if character != "'":
            continue
        previous = characters[index - 1] if index else " "
        following = characters[index + 1] if index + 1 < len(characters) else " "
        if opening is None and not previous.isalnum():
            opening = index
        elif opening is not None and not following.isalnum():
            characters[opening : index + 1] = " " * (index + 1 - opening)
            opening = None
    return "".join(characters)


def _direct_partner_terms(dialogue):
    terms = {
        "boyfriend": "boyfriend",
        "boyfriends": "boyfriend",
        "girlfriend": "girlfriend",
        "girlfriends": "girlfriend",
    }
    results = []
    unquoted = _mask_quoted_dialogue(dialogue).replace("’", "'")
    for sentence in re.split(r"[.!?]+", unquoted):
        tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", sentence)
        for index, token in enumerate(tokens):
            term = terms.get(token)
            if term and _direct_partner_prefix(tokens[:index]):
                results.append(term)
    return results


def _direct_partner_prefix(prefix):
    ownership = bool(prefix) and prefix[-1] in ("my", "a")
    if prefix in (["let's", "be"], ["be", "my"], ["become", "my"]):
        return True
    if prefix in (["please", "be", "my"], ["please", "become", "my"]):
        return True
    if not ownership:
        return False
    stem = prefix[:-1]
    if stem == ["you're"]:
        return True
    if stem[0:2] == ["you", "are"]:
        modifiers = stem[2:]
        return not modifiers or modifiers in (
            ["definitely"],
            ["certainly"],
            ["really"],
            ["truly"],
        )
    if stem in (
        ["you", "were"],
        ["you", "will", "be"],
        ["you", "would", "be"],
        ["you", "could", "be"],
        ["you", "can", "be"],
        ["you", "have", "been"],
        ["you", "have", "always", "been"],
    ):
        return True
    if len(stem) >= 2 and stem[0] in ("will", "would", "could", "can"):
        if stem[1] != "you":
            return False
        proposal = stem[2:]
        if proposal[0:1] == ["please"]:
            proposal = proposal[1:]
        return proposal in (
            ["be"],
            ["become"],
            ["like", "to", "be"],
            ["like", "to", "become"],
            ["want", "to", "be"],
            ["want", "to", "become"],
        )
    return stem in (
        ["i", "want", "you", "to", "be"],
        ["i", "want", "you", "to", "become"],
        ["i", "would", "like", "you", "to", "be"],
        ["i", "would", "like", "you", "to", "become"],
    )


def response_has_role_confusion(response, context):
    dialogue = str(response.get("dialogue") or "")
    normalized_dialogue = dialogue.casefold().replace("’", "'")
    words = set(re.findall(r"\w+", normalized_dialogue))
    speaker_name = str(context.get("speaker", {}).get("name") or "").casefold()
    speaker = set(re.findall(r"\w+", speaker_name))
    listener = set(
        re.findall(r"\w+", str(context.get("listener", {}).get("name") or "").casefold())
    )
    asks_speaker_name = re.search(
        r"\byour (?:full )?name\b",
        str(context.get("message") or "").casefold(),
    )
    self_identifies = any(
        re.search(
            rf"\b(?:my name is|i am|i'm|call me)\s+{re.escape(name)}\b",
            normalized_dialogue,
        )
        for name in (speaker_name, speaker_name.split()[0] if speaker_name else "")
        if name
    )
    if (
        {word for word in speaker - listener if len(word) > 1} & words
        and not asks_speaker_name
        and not self_identifies
    ):
        return True
    gender = _identity_gender(context.get("listener_identity") or {})
    expected = "boyfriend" if gender == "male" else "girlfriend"
    return any(gender == "unknown" or term != expected for term in _direct_partner_terms(dialogue))


def _dialogue_words(value, context):
    names = set()
    for role in ("speaker", "listener"):
        names.update(
            re.findall(
                r"[a-z0-9']+",
                str(context.get(role, {}).get("name") or "").casefold(),
            )
        )
    return [
        word for word in re.findall(r"[a-z0-9']+", str(value or "").casefold()) if word not in names
    ]


def _dialogue_similarity(left, right):
    if not left or not right:
        return 0.0
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    sequence_ratio = matcher.ratio()
    overlap_ratio = sum((Counter(left) & Counter(right)).values()) / min(len(left), len(right))
    blocks = [block.size for block in matcher.get_matching_blocks() if block.size]
    longest_length = max(len(left), len(right))
    secondary_coverage = (sum(blocks) - max(blocks, default=0)) / longest_length
    total_matching_coverage = sum(blocks) / longest_length
    if secondary_coverage >= 0.25 and total_matching_coverage >= 0.55:
        return 1 - (1 - sequence_ratio) * (1 - overlap_ratio)
    return max(sequence_ratio, overlap_ratio)


def explicit_social_category(message):
    value = str(message or "").casefold()
    patterns = (
        (
            "romance",
            r"\b(date|kiss|marry|girlfriend|boyfriend|attracted|attractive|beautiful|"
            r"gorgeous|handsome|hot|sexy|love you|feelings for|like you romantically)\b",
        ),
        ("mean", r"\b(hate|despise|idiot|stupid|insufferable|leave me alone|go away)\b"),
        (
            "mischief",
            r"\b(prank|trick|scare|deceive|pretend|lie|lies|lied|lying|mess with)\b",
        ),
        ("funny", r"\b(jokes?|funn(?:y|ier|iest)|hilarious|laugh|pun|comedy)\b"),
    )
    return next(
        (category for category, pattern in patterns if re.search(pattern, value)),
        None,
    )


def classify_social_category(message):
    return explicit_social_category(message) or "friendly"


def response_category_issue(response):
    dialogue = str(response.get("dialogue") or "")
    category = str(response.get("response_category") or "")
    explicit = explicit_social_category(dialogue)
    if explicit is not None and explicit != category:
        return f"explicit {explicit}"
    tone = {str(tag).casefold() for tag in response.get("tone_tags") or []}
    tone.add(str(response.get("expressed_emotion") or response.get("emotion") or "").casefold())
    if category == "romance" and explicit is None and tone & {"hesitant", "uncertain", "hostile"}:
        return "non-romantic tone"
    return ""


def classify_player_interaction(message):
    if _is_romantic_request(message):
        return "romantic_invitation"
    category = explicit_social_category(message)
    if category == "romance":
        return "romantic_compliment"
    if category == "mean":
        return "hostile"
    value = str(message or "").casefold()
    if "?" in value:
        return "informational"
    if re.search(r"\b(friend|friends|nice|kind|hello|hi|thank|glad to meet)\b", value):
        return "friendly"
    return "neutral"


def _is_romantic_request(message):
    return bool(
        re.search(
            r"\b(go(?:ing)? out|go on a date|on a date with|date me|"
            r"take (?:you|them|him|her) on a date|"
            r"be my (?:girl|boy)friend|be (?:girl|boy)friends|kiss me|marry me|"
            r"be together)\b",
            str(message or "").casefold(),
        )
    )


def _conversation_copy_issue(dialogue_words, message_words, context):
    for turn in context.get("conversation") or []:
        previous_message = _dialogue_words(turn.get("message"), context)
        if (
            len(previous_message) >= 6
            and len(dialogue_words) >= 4
            and _dialogue_similarity(dialogue_words, previous_message) >= 0.72
        ):
            return "do not copy a previous player message"
        previous_reply = _dialogue_words(turn.get("dialogue"), context)
        if (
            len(previous_reply) >= 4
            and len(dialogue_words) >= 4
            and previous_message != message_words
            and _dialogue_similarity(dialogue_words, previous_reply) >= 0.72
        ):
            return "do not reuse a previous reply for a different message"
    return ""


def _listener_name_issue(dialogue, context):
    listener_name = str(context.get("listener", {}).get("name") or "").strip()
    asks_listener_name = re.search(
        r"\b(?:what(?:'s| is) your (?:full )?name|tell me your (?:full )?name)\b",
        dialogue.replace("’", "'"),
    )
    if listener_name and asks_listener_name:
        return "do not ask for the known Listener's name"
    return ""


_RECALL_UNCERTAINTY_PHRASES = (
    "don't know",
    "do not know",
    "not sure",
    "don't remember",
    "do not remember",
    "what are you talking",
)


def _recall_uncertainty_issue(message, dialogue, context):
    asks_recalled_fact = analyze_recall_query(message).explicit
    has_evidence = _memory_supports_question(message, context)
    expresses_uncertainty = any(phrase in dialogue for phrase in _RECALL_UNCERTAINTY_PHRASES)
    if asks_recalled_fact and has_evidence and expresses_uncertainty:
        return "use the supporting memory instead of denying it"
    if asks_recalled_fact and not has_evidence and not expresses_uncertainty:
        return "state uncertainty because no supporting memory exists"
    return ""


def response_grounding_issue(payload, response, context):
    message = str(payload.get("message") or "").casefold()
    dialogue = str(response.get("dialogue") or "").casefold()
    message_words = _dialogue_words(message, context)
    dialogue_words = _dialogue_words(dialogue, context)
    if (
        len(message_words) >= 6
        and len(dialogue_words) >= 4
        and _dialogue_similarity(message_words, dialogue_words) >= 0.72
    ):
        return "respond naturally; do not copy the player's message"
    conversation_copy_issue = _conversation_copy_issue(dialogue_words, message_words, context)
    if conversation_copy_issue:
        return conversation_copy_issue
    listener_name_issue = _listener_name_issue(dialogue, context)
    if listener_name_issue:
        return listener_name_issue
    supported_recall_issue = _supported_recall_issue(payload, response, context)
    if supported_recall_issue:
        return supported_recall_issue
    return _recall_uncertainty_issue(message, dialogue, context)


_IDENTIFIER_TOKEN = re.compile(r"\b(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+\b", re.IGNORECASE)


def _identifier_tokens(text):
    return {match.group(0).casefold() for match in _IDENTIFIER_TOKEN.finditer(str(text or ""))}


def _primary_fact_keys(memories):
    return {
        (
            str(fact.get("actor_id") or ""),
            str(fact.get("statement") or "").strip(),
        )
        for memory in memories
        if memory.get("semantic_primary") is True
        for fact in memory.get("facts") or []
        if isinstance(fact, dict) and str(fact.get("statement") or "").strip()
    }


def _recalled_facts(memories):
    return [
        {
            "actor_id": str(fact.get("actor_id") or ""),
            "statement": str(fact.get("statement") or "").strip(),
        }
        for memory in memories
        for fact in memory.get("facts") or []
        if isinstance(fact, dict) and str(fact.get("statement") or "").strip()
    ]


def _identifier_filtered_facts(facts, identifiers):
    if not identifiers:
        return facts
    return [fact for fact in facts if identifiers <= _identifier_tokens(fact["statement"])]


def _lexical_recall_facts(facts, primary, message, context):
    question_terms = set(_dialogue_words(message, context))
    lexical = [
        fact for fact in facts if question_terms & set(_dialogue_words(fact["statement"], context))
    ]
    primary_lexical = [fact for fact in lexical if fact in primary]
    if primary_lexical:
        return primary_lexical
    return lexical or primary


def _supported_recall_facts(message, context):
    query = analyze_recall_query(str(message or ""))
    memories = list(context.get("recalled_memories") or [])
    primary_keys = _primary_fact_keys(memories)
    identifiers = _identifier_tokens(message)
    facts = _recalled_facts(memories)
    owner_id = empneon_state.codeword_recall_owner_id(
        message,
        str(context.get("speaker_id") or ""),
        str(context.get("listener_id") or ""),
    )
    if owner_id is not None:
        facts = [fact for fact in facts if fact["actor_id"] == owner_id]
    facts = _identifier_filtered_facts(facts, identifiers)
    primary = [fact for fact in facts if (fact["actor_id"], fact["statement"]) in primary_keys]
    if not query.explicit:
        return primary
    supporting = [fact for fact in facts if fact_supports_query(fact, query)]
    if supporting:
        return supporting
    return _lexical_recall_facts(facts, primary, message, context)


_CODEWORD_FACT = re.compile(
    r"\b(?P<possessive>my|our|your)\s+(?:secret\s+)?code\s*word\s+"
    r"(?:is|are)\s+(?P<identifier>(?=[A-Z0-9-]*\d)"
    r"[A-Z0-9]+(?:-[A-Z0-9]+)+)\b",
    re.IGNORECASE,
)


def _codeword_fact_parts(fact):
    match = _CODEWORD_FACT.search(str(fact.get("statement") or ""))
    if match is None:
        return None
    return match.group("possessive").casefold(), match.group("identifier")


def _attributed_fact_text(fact, context):
    actor_id = str(fact.get("actor_id") or "")
    names = {
        context.get("speaker_id"): context["speaker"].get("name") or UNKNOWN_ACTOR_NAME,
        context.get("listener_id"): context["listener"].get("name") or UNKNOWN_ACTOR_NAME,
    }
    actor = names.get(actor_id, actor_id or UNKNOWN_ACTOR_NAME)
    parts = _codeword_fact_parts(fact)
    if parts is not None:
        possessive, identifier = parts
        if possessive == "our":
            return f"The shared code word is {identifier}."
        return f"{actor}'s code word is {identifier}."
    return "{} said: {}".format(actor, fact["statement"])


def _recalled_fact_dialogue(fact, context, message=""):
    actor_id = str(fact.get("actor_id") or "")
    statement = fact["statement"]
    parts = _codeword_fact_parts(fact)
    owner_id = empneon_state.codeword_recall_owner_id(
        message,
        str(context.get("speaker_id") or ""),
        str(context.get("listener_id") or ""),
    )
    if parts is not None and owner_id is not None:
        pronoun = "My" if owner_id == str(context.get("speaker_id") or "") else "Our"
        return f"{pronoun} code word is {parts[1]}."
    if actor_id == context.get("listener_id"):
        return f'You told me: "{statement}"'
    if actor_id == context.get("speaker_id"):
        return f'I remember saying: "{statement}"'
    names = {
        context.get("speaker_id"): context["speaker"].get("name") or "",
        context.get("listener_id"): context["listener"].get("name") or "",
    }
    actor = names.get(actor_id, actor_id)
    if actor:
        return f'{actor} said: "{statement}"'
    return f'I remember this: "{statement}"'


_PREFERENCE_FACT = re.compile(
    r"\bi prefer (?P<preferred>.+?) to (?P<alternative>[^.!?]+)(?:[.!?]|$)",
    re.IGNORECASE,
)
_PROMISE_FACT = re.compile(
    r"\bi promise(?: that)? (?P<commitment>[^.!?]+)(?:[.!?]|$)",
    re.IGNORECASE,
)


def _preference_issue(facts, dialogue, context):
    preferences = [
        match
        for fact in facts
        if (match := _PREFERENCE_FACT.search(str(fact.get("statement") or "")))
    ]
    if not preferences:
        return ""
    statements = re.split(r"(?<=[.!?])\s+", str(dialogue or ""))
    for preference in preferences:
        preferred = set(_dialogue_words(preference.group("preferred"), context))
        if any(
            not statement.rstrip().endswith("?")
            and preferred <= set(_dialogue_words(statement, context))
            and re.search(
                r"\b(?:prefer|best|suit|choice|choose|pick|recommend)\w*\b",
                statement,
                re.IGNORECASE,
            )
            for statement in statements
        ):
            return ""
    return "answer with the supported preference"


def _promise_issue(facts, dialogue, context):
    promises = [
        match for fact in facts if (match := _PROMISE_FACT.search(str(fact.get("statement") or "")))
    ]
    if not promises:
        return ""
    statements = re.split(r"(?<=[.!?])\s+", str(dialogue or ""))
    ignored = {"a", "an", "i", "i'll", "it", "my", "our", "the", "to", "will"}
    for promise in promises:
        details = {
            word
            for word in _dialogue_words(
                promise.group("commitment"),
                context,
            )
            if word not in ignored
        }
        if details and any(
            not statement.rstrip().endswith("?")
            and details <= set(_dialogue_words(statement, context))
            for statement in statements
        ):
            return ""
    return "answer with the complete supported promise"


_ANSWER_TERM_IGNORED_WORDS = {
    "about",
    "can",
    "did",
    "does",
    "good",
    "going",
    "know",
    "remember",
    "said",
    "say",
    "sound",
    "sounds",
    "tell",
    "that",
    "the",
    "this",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "would",
    "you",
}


def _owner_codeword_issue(message, facts, dialogue, context):
    owner_id = empneon_state.codeword_recall_owner_id(
        message,
        str(context.get("speaker_id") or ""),
        str(context.get("listener_id") or ""),
    )
    if (
        owner_id == str(context.get("speaker_id") or "")
        and any(_codeword_fact_parts(fact) is not None for fact in facts)
        and not re.search(
            r"\bmy\s+(?:secret\s+)?code\s*word\b",
            dialogue,
            re.IGNORECASE,
        )
    ):
        return "refer to the Speaker-owned code word in first person as my code word"
    return ""


def _unanswered_recall_issue(statements, message, dialogue, context):
    question_terms = set(_dialogue_words(message, context))
    answer_terms = set().union(
        *(
            set(_dialogue_words(statement, context)) - question_terms - _ANSWER_TERM_IGNORED_WORDS
            for statement in statements
        )
    )
    if answer_terms and answer_terms & set(_dialogue_words(dialogue, context)):
        return ""
    return "answer the recall question with the selected attributed fact"


def _supported_recall_issue(payload, response, context):
    message = str(payload.get("message") or "")
    query = analyze_recall_query(message)
    if "?" not in message and not re.search(
        r"\b(?:tell|remind)\s+me\b", message, re.IGNORECASE
    ):
        return ""
    facts = _supported_recall_facts(message, context)
    if not facts:
        return ""
    statements = [fact["statement"] for fact in facts]
    dialogue = str(response.get("dialogue") or "")
    lowered = dialogue.casefold()
    if any(phrase in lowered for phrase in _RECALL_UNCERTAINTY_PHRASES):
        return "use the supporting memory instead of denying it"
    issue = validate_recall_response(
        query,
        facts,
        dialogue,
        str(context.get("speaker_id") or ""),
        str(context.get("listener_id") or ""),
    )
    if issue:
        return issue
    issue = _preference_issue(facts, dialogue, context)
    if issue:
        return issue
    issue = _promise_issue(facts, dialogue, context)
    if issue:
        return issue
    issue = _owner_codeword_issue(message, facts, dialogue, context)
    if issue:
        return issue
    if "time" in query.requested_slots:
        return ""
    return _unanswered_recall_issue(statements, message, dialogue, context)


def _memory_supports_question(message, context):
    facts = _supported_recall_facts(message, context)
    if analyze_recall_query(str(message or "")).explicit:
        return bool(facts)
    if facts:
        return True
    ignored = {
        "where",
        "when",
        "who",
        "what",
        "which",
        "remember",
        "said",
        "say",
        "item",
        "hidden",
        "there",
        "about",
    }
    terms = {
        term
        for term in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(message).casefold())
        if len(term) >= 4 and term not in ignored
    }
    evidence = _recalled_memory_text(context).casefold()
    return bool(terms and any(term in evidence for term in terms))


def _fallback_supported_fact_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if "?" in message and supported_facts:
        dialogue = _recalled_fact_dialogue(supported_facts[0], context, message)
        return dialogue, "confident", "recall", 0
    return None


def _fallback_romantic_invitation_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if interaction_kind == "romantic_invitation":
        return "No, I would rather stay friends.", "awkward", "set_boundary", 0
    return None


def _fallback_recalled_memory_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if "?" in message and _memory_supports_question(message, context):
        candidates = [
            str(item.get(field) or "").strip()
            for item in context.get("recalled_memories") or []
            for field in ("message", "dialogue")
            if str(item.get(field) or "").strip()
        ]
        dialogue = next((item for item in candidates if not item.endswith("?")), candidates[0])
        return dialogue, "confident", "recall", 0
    return None


def _fallback_unsupported_recall_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if analyze_recall_query(message).explicit and not _memory_supports_question(message, context):
        return "I don't know or remember that.", "uncertain", "admit_uncertainty", 0
    return None


def _fallback_avoidance_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if any(word in message for word in ("avoid", "avoiding", "ignored", "ignore")):
        return (
            "I wasn't trying to avoid you. I just needed a little space to sort through my feelings.",
            "tense",
            "reassure",
            0,
        )
    return None


def _fallback_apology_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if any(word in message for word in ("sorry", "apologize", "forgive")):
        return "I appreciate you saying that. I need time, but I'm listening.", "softened", "accept_apology", 1
    return None


def _fallback_funny_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if incoming_category == "funny":
        return (
            "Here's a llama joke: What do llamas call a rushed vacation? An alpaca-to-go.",
            "playful",
            "tell_joke",
            0,
        )
    return None


def _fallback_mischief_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if incoming_category == "mischief":
        return (
            "How about a harmless trick: tell them the llama council promoted "
            "them to Chief Snack Officer?",
            "playful",
            "suggest_prank",
            0,
        )
    return None


def _fallback_hostile_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if interaction_kind == "hostile":
        return (
            "I won't continue this conversation while you speak to me that way.",
            "tense",
            "set_boundary",
            -1,
        )
    return None


def _fallback_romantic_compliment_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if interaction_kind == "romantic_compliment":
        return "That is flattering. Thank you for being honest with me.", "flattered", "acknowledge_flirtation", 0
    return None


def _fallback_intimacy_boundary_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if any(word in message for word in ("sex", "woohoo")):
        return (
            "Slow down. If there is something between us, I want it to feel right, not rushed.",
            "awkward",
            "set_boundary",
            -1,
        )
    return None


def _fallback_informational_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if interaction_kind == "informational":
        return (
            "I may not have every answer, but I'll tell you what I know.",
            context.get("emotions", {}).get("current_mood", "neutral"),
            "respond",
            0,
        )
    return None


def _fallback_friendly_reply(message, interaction_kind, supported_facts, incoming_category, context):
    if interaction_kind == "friendly":
        return "It's good to hear that. I enjoy talking with you.", "happy", "respond", 0
    return None


_FALLBACK_CONTENT_CHECKS = (
    _fallback_supported_fact_reply,
    _fallback_romantic_invitation_reply,
    _fallback_recalled_memory_reply,
    _fallback_unsupported_recall_reply,
    _fallback_avoidance_reply,
    _fallback_apology_reply,
    _fallback_funny_reply,
    _fallback_mischief_reply,
    _fallback_hostile_reply,
    _fallback_romantic_compliment_reply,
    _fallback_intimacy_boundary_reply,
    _fallback_informational_reply,
    _fallback_friendly_reply,
)


def _reasoning_fallback_content(message, interaction_kind, supported_facts, incoming_category, context):
    for check in _FALLBACK_CONTENT_CHECKS:
        result = check(message, interaction_kind, supported_facts, incoming_category, context)
        if result is not None:
            return result
    return (
        "I hear you. Thank you for telling me.",
        context.get("emotions", {}).get("current_mood", "neutral"),
        "respond",
        0,
    )


def _reasoning_fallback_retry_dialogue(message, dialogue, context):
    candidates = []
    if "?" in message and _memory_supports_question(message, context):
        candidates.append(f"Here is the detail I remember: {dialogue}")
    elif analyze_recall_query(message).explicit:
        candidates.append("I'm not sure; I don't remember enough to answer that.")
    candidates.extend(
        (
            "Let me think about that in my own words.",
            "I understand. Give me a moment to respond.",
            "There is more I want to consider before I answer.",
        )
    )
    return candidates


def _reasoning_fallback_retry(payload, fallback, dialogue, message, context, grounding_issue, role_confusion):
    for candidate_dialogue in _reasoning_fallback_retry_dialogue(message, dialogue, context):
        candidate = dict(fallback, dialogue=candidate_dialogue)
        if not grounding_issue(payload, candidate, context) and not role_confusion(candidate, context):
            return candidate
    return None


def reasoning_fallback_response(
    payload,
    context,
    grounding_issue=response_grounding_issue,
    role_confusion=response_has_role_confusion,
):
    message = str(payload.get("message") or "").lower()
    interaction_kind = classify_player_interaction(message)
    supported_facts = _supported_recall_facts(message, context)
    incoming_category = str(payload.get("incoming_category") or classify_social_category(message))
    fallback_category, tone_tag = {
        "romance": ("friendly", "reserved"),
        "mean": ("mean", "firm"),
        "mischief": ("mischief", "wary"),
        "funny": ("funny", "light"),
        "friendly": ("friendly", "neutral"),
    }.get(incoming_category, ("friendly", "neutral"))
    dialogue, emotion, intent, trust_delta = _reasoning_fallback_content(
        message, interaction_kind, supported_facts, incoming_category, context
    )
    fallback = normalize_response(
        {
            "dialogue": dialogue,
            "emotion": emotion,
            "intent": intent,
            "response_category": fallback_category,
            "tone_tags": [tone_tag],
            "trust_delta": trust_delta,
            "memory": {
                "importance": 0.2,
                "summary": "{} {}".format(payload.get("message") or "", dialogue).strip(),
            },
        },
    )
    fallback["suggested_action"] = fallback["animation"] = "none"
    if not grounding_issue(payload, fallback, context) and not role_confusion(fallback, context):
        return fallback

    retry = _reasoning_fallback_retry(payload, fallback, dialogue, message, context, grounding_issue, role_confusion)
    if retry is not None:
        return retry
    return dict(
        fallback,
        dialogue="I need to pause this conversation for now.",
        emotion="guarded",
        intent="set_boundary",
        response_category="friendly",
        tone_tags=["reserved"],
        trust_delta=0,
    )


def _response_rejection_diagnostics(value):
    if not isinstance(value, list) or len(value) != 2:
        return []
    diagnostics = []
    for expected_attempt, item in enumerate(value, start=1):
        if (
            not isinstance(item, dict)
            or type(item.get("attempt")) is not int
            or item["attempt"] != expected_attempt
            or not isinstance(item.get("reason"), str)
            or not item["reason"].strip()
        ):
            return []
        diagnostics.append({"attempt": expected_attempt, "reason": item["reason"].strip()})
    return diagnostics


class CognitionRuntime:
    def __init__(
        self,
        generate,
        rejection_enabled,
        log_warning,
        grounding_issue=response_grounding_issue,
        role_confusion=response_has_role_confusion,
        reasoning_fallback=reasoning_fallback_response,
    ):
        self._generate = generate
        self._rejection_enabled = rejection_enabled
        self._log_warning = log_warning
        self._grounding_issue = grounding_issue
        self._role_confusion = role_confusion
        self._reasoning_fallback = reasoning_fallback

    def _generate_or_none(self, prompt, categories, supported_facts):
        try:
            return self._generate(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                schema=dialogue_schema(categories),
                schema_name="sims_dialogue",
                task="large",
            )
        except (ProviderError, OSError):
            if supported_facts:
                return None
            raise

    def _normalized_attempt_response(self, content, categories):
        try:
            return normalize_response(extract_json(content), categories)
        except ValueError:
            return fallback_response(content, categories)

    def _apply_response_overrides(self, payload, response, categories, supported_facts):
        explicit_category = explicit_social_category(response["dialogue"])
        if (
            self._rejection_enabled()
            and explicit_category in categories
            and explicit_category != response["response_category"]
        ):
            response["response_category"] = explicit_category
            response["relationship_outcome"] = validated_relationship_outcome(response)
            response["suggested_action"] = response["animation"] = "none"
        if payload.get("incoming_category") == "funny" and response["response_category"] in (
            "friendly",
            "funny",
        ):
            response["trust_delta"] = 0
            response["relationship_outcome"] = "none"
            response["suggested_action"] = response["animation"] = "none"
        if supported_facts:
            response["relationship_outcome"] = "none"
            response["suggested_action"] = response["animation"] = "none"
        return response

    def _response_issues(self, payload, response, context, recall_issue):
        if self._rejection_enabled():
            issue = self._grounding_issue(payload, response, context)
            category_issue = response_category_issue(response)
            role_confusion = self._role_confusion(response, context)
        else:
            issue = recall_issue
            category_issue = ""
            role_confusion = False
        return issue, category_issue, role_confusion

    def _augment_prompt_with_corrections(
        self, prompt, context, issue, recall_issue, category_issue, supported_facts
    ):
        if self._rejection_enabled():
            prompt += (
                "\nCorrection: Dialogue must not contain the Speaker's name, '{}'. "
                "If using a name, use the Listener's name, '{}'."
            ).format(context["speaker"]["name"], context["listener"]["name"])
        if issue:
            prompt += f"\nCorrection: {issue}."
        if recall_issue:
            prompt += (
                "\nCorrection: Answer the recall question using this "
                "attributed evidence: "
                + " | ".join(_attributed_fact_text(fact, context) for fact in supported_facts)
            )
        if category_issue:
            prompt += (
                "\nCorrection: The response_category must describe the Speaker's own "
                "dialogue. Do not copy the incoming category when the Speaker rejects or "
                "changes direction."
            )
        if issue and ("copy" in issue or "previous reply" in issue):
            prompt += (
                "\nCorrection: Keep the facts and conversational continuity, but advance the "
                "conversation with a new reaction, detail, question, or decision. Do not reuse "
                "an earlier opening or sentence frame."
            )
        return prompt

    def dialogue(self, payload, context):
        configured_categories = payload.get("available_response_categories")
        categories = available_response_categories(configured_categories)
        if configured_categories is not None and not categories:
            return self._reasoning_fallback(payload, context)
        if configured_categories is None:
            categories = SOCIAL_CATEGORIES
        prompt = build_chat_prompt(payload, context)
        supported_facts = _supported_recall_facts(payload.get("message"), context)
        rejections = []
        for attempt in range(2):
            content = self._generate_or_none(prompt, categories, supported_facts)
            if content is None:
                return self._reasoning_fallback(payload, context)
            response = self._normalized_attempt_response(content, categories)
            self._apply_response_overrides(payload, response, categories, supported_facts)
            recall_issue = _supported_recall_issue(payload, response, context)
            if not self._rejection_enabled() and not recall_issue:
                return response
            issue, category_issue, role_confusion = self._response_issues(
                payload, response, context, recall_issue
            )
            if not role_confusion and not issue and not category_issue:
                return response
            reason = issue or category_issue or "speaker/listener confusion"
            self._log_warning(
                "model response failed grounding (%s); retrying=%s",
                reason,
                attempt == 0,
            )
            rejections.append({"attempt": attempt + 1, "reason": reason})
            prompt = self._augment_prompt_with_corrections(
                prompt, context, issue, recall_issue, category_issue, supported_facts
            )
        fallback = self._reasoning_fallback(payload, context)
        fallback["suggested_action"] = fallback["animation"] = "none"
        fallback["_response_rejections"] = rejections
        return fallback

    def story_beat(self, prompt):
        content = self._generate(
            [
                {
                    "role": "system",
                    "content": "You are a Sims 4 AI Director. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            schema=DIRECTOR_SCHEMA,
            schema_name="sims_director",
            task="small",
        )
        try:
            raw = extract_json(content)
        except ValueError:
            raw = {
                "hook": str(content).strip()[:500],
                "target": "",
                "suggested_action": "",
                "tone": "neutral",
            }
        return {
            "hook": str(raw.get("hook") or "").strip(),
            "target": str(raw.get("target") or "").strip(),
            "suggested_action": str(raw.get("suggested_action") or "").strip(),
            "tone": str(raw.get("tone") or "neutral").strip(),
        }
