# Provider-Agnostic Structured Output Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JSON Schema a reliable Empneon Core provider contract, enforce it through LM Studio structured output, and retain narrow Sims category aliases as defensive compatibility.

**Architecture:** `GenerationRequest.schema` remains game and model agnostic. The configured router rejects providers that claim no structured-output support, while each capable provider translates the unchanged schema to its native API; LM Studio schema requests use `/v1/chat/completions`, and schema-free requests retain `/api/v1/chat`. The Sims adapter applies only explicit legacy aliases before validating against its game-provided category list.

**Tech Stack:** Python 3.12, stdlib `asyncio`/`json`/`urllib`, pytest

## Global Constraints

- Empneon Core must contain no Sims-specific categories or gameplay rules.
- Provider code must contain no game-specific schema vocabulary.
- Schema-free LM Studio requests must preserve existing native endpoint behavior.
- Unknown or unavailable Sims response categories must remain rejected.
- Do not add dependencies or abstractions.
- Do not commit or push until the user explicitly requests it.

---

## File Structure

- Modify `core/src/empneon/providers/llm/configured.py`: enforce the provider capability contract at the routing boundary.
- Modify `core/src/empneon/providers/llm/lmstudio.py`: translate schema requests to LM Studio's structured-output endpoint.
- Modify `core/tests/unit/test_openai_compatible_provider.py`: verify routing, payloads, response parsing, and unchanged schema-free behavior.
- Modify `adapters/thesims4/backend/ai_sims_server.py`: consistently normalize known legacy response-category aliases.
- Modify `adapters/thesims4/tests/test_sims4_backend.py`: reproduce the live failure and cover friendly, mean, romantic, and unknown categories.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: record the automated fix and required live retest.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-results.md`: record the failure cause and automated verification result.

### Task 1: Enforce the Core structured-output contract

**Files:**
- Modify: `core/src/empneon/providers/llm/configured.py`
- Test: `core/tests/unit/test_openai_compatible_provider.py`

**Interfaces:**
- Consumes: `GenerationRequest.schema: dict[str, object] | None` and `LLMProvider.capabilities.structured_output`
- Produces: `ConfiguredProviderRouter.generate_result(...)` either forwards the unchanged schema to a capable provider or raises `ProviderError`

- [ ] **Step 1: Write failing router contract tests**

Add providers that record requests and advertise opposite capabilities:

```python
def test_router_preserves_schema_for_capable_provider(monkeypatch) -> None:
    schema = {"type": "object", "properties": {"category": {"enum": ["calm"]}}}
    requests = []

    class Provider:
        capabilities = ModelCapabilities(structured_output=True)

        async def generate(self, request):
            requests.append(request)
            return GenerationResult('{"category":"calm"}')

    router = ConfiguredProviderRouter(
        "test",
        {"test": {"endpoint": "http://localhost", "model": "stub"}},
        {"large": {}},
    )
    monkeypatch.setattr(router, "provider_for", lambda _task: Provider())

    asyncio.run(
        router.generate_result(
            "large", (Message("user", "respond"),), schema=schema
        )
    )

    assert requests[0].schema is schema


def test_router_rejects_schema_for_incapable_provider(monkeypatch) -> None:
    class Provider:
        capabilities = ModelCapabilities()

        async def generate(self, _request):
            raise AssertionError("unsupported structured request must not be sent")

    router = ConfiguredProviderRouter(
        "test",
        {"test": {"endpoint": "http://localhost", "model": "stub"}},
        {"large": {}},
    )
    monkeypatch.setattr(router, "provider_for", lambda _task: Provider())

    with pytest.raises(ProviderError, match="structured output"):
        asyncio.run(
            router.generate_result(
                "large",
                (Message("user", "respond"),),
                schema={"type": "object"},
            )
        )
```

- [ ] **Step 2: Run the focused tests and verify the unsupported-provider test fails**

Run:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_openai_compatible_provider.py -k "router_preserves_schema or router_rejects_schema"
```

Expected: the capable-provider test passes through existing request construction; the incapable-provider test fails because generation is attempted.

- [ ] **Step 3: Add the minimal capability guard**

In `ConfiguredProviderRouter.generate_result`, resolve the provider once and guard schema requests:

```python
provider = self.provider_for(task)
if schema is not None and not provider.capabilities.structured_output:
    raise ProviderError("provider does not support structured output")
request = self.generation_request(
    task, messages, schema=schema, temperature=temperature
)
return await provider.generate(request)
```

- [ ] **Step 4: Run the focused router tests**

Run the Step 2 command.

Expected: `2 passed`.

### Task 2: Send LM Studio schemas through constrained structured output

**Files:**
- Modify: `core/src/empneon/providers/llm/lmstudio.py`
- Test: `core/tests/unit/test_openai_compatible_provider.py`

**Interfaces:**
- Consumes: `GenerationRequest` with optional `schema`
- Produces: `LMStudioProvider.generate(...) -> GenerationResult`; schema requests use `/v1/chat/completions`, schema-free requests use `/api/v1/chat`

- [ ] **Step 1: Write the failing structured-output transport test**

```python
def test_lmstudio_provider_enforces_schema_through_chat_completions() -> None:
    schema = {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": ["friendly", "romance"]}},
        "required": ["category"],
    }
    models = {"models": [{"key": "gemma", "loaded_instances": [{"id": "gemma-loaded"}]}]}
    completion = {
        "choices": [{"message": {"content": '{"category":"friendly"}'}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5},
    }

    with patch(
        "urllib.request.urlopen", side_effect=[Response(models), Response(completion)]
    ) as urlopen:
        provider = LMStudioProvider(
            "http://localhost:1234/api/v1", "local-model"
        )
        result = asyncio.run(
            provider.generate(
                GenerationRequest(
                    (Message("system", "act"), Message("user", "hello")),
                    120,
                    0.4,
                    schema,
                )
            )
        )

    request = urlopen.call_args_list[1].args[0]
    assert provider.capabilities.structured_output is True
    assert request.full_url == "http://localhost:1234/v1/chat/completions"
    assert json.loads(request.data) == {
        "model": "gemma-loaded",
        "messages": [
            {"role": "system", "content": "act"},
            {"role": "user", "content": "hello"},
        ],
        "max_tokens": 120,
        "temperature": 0.4,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": schema},
        },
    }
    assert result.content == '{"category":"friendly"}'
    assert result.prompt_tokens == 20
    assert result.completion_tokens == 5
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_openai_compatible_provider.py::test_lmstudio_provider_enforces_schema_through_chat_completions
```

Expected: FAIL because LM Studio still posts to `/api/v1/chat`, omits `response_format`, and advertises no structured output.

- [ ] **Step 3: Implement the structured branch with no new abstraction**

Set the capability:

```python
return ModelCapabilities(structured_output=True, local=True)
```

At the start of `_generate`, branch only for schema requests:

```python
if request.schema is not None:
    return self._generate_structured(request)
```

Add the focused helper:

```python
def _generate_structured(self, request: GenerationRequest) -> GenerationResult:
    started = time.perf_counter()
    data = self._request(
        "/chat/completions",
        {
            "model": self._model_id(),
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": request.schema},
            },
        },
        native=False,
    )
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return GenerationResult(
        content=str(content),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
    )
```

Extend `_request` without changing its default callers:

```python
def _request(
    self,
    path: str,
    body: dict[str, object] | None = None,
    *,
    native: bool = True,
) -> dict[str, object]:
    root = self.base_url.rstrip("/")
    if root.endswith("/api/v1"):
        root = root[: -len("/api/v1")]
    prefix = "/api/v1" if native else "/v1"
    request = urllib.request.Request(
        f"{root}{prefix}{path}",
        ...
    )
```

- [ ] **Step 4: Run all provider tests**

Run:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_openai_compatible_provider.py
```

Expected: all tests pass, including the unchanged native LM Studio payload tests.

### Task 3: Normalize only explicit Sims legacy aliases

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: model `response_category` plus the game-provided `available_categories`
- Produces: a normalized category only for the existing explicit alias map; unknown or unavailable values raise `ValueError`

- [ ] **Step 1: Add failing regression and alias-boundary tests**

Replace the old dialogue-keyword expectation with the approved alias behavior and add the exact live response:

```python
def test_friendship_category_alias_preserves_valid_live_response() -> None:
    dialogue = (
        "That's funny! You are wonderful too, Bernard. "
        "Beers sound perfect right now!"
    )
    response = ai_sims_server.normalize_response(
        {
            "dialogue": dialogue,
            "expressed_emotion": "playful",
            "intent": "accept_playfully",
            "response_category": "friendship",
            "tone_tags": ["playful", "friendly"],
            "trust_delta": 1,
            "relationship_outcome": "friendship_positive",
        },
        ["friendly", "romance"],
    )

    assert response["dialogue"] == dialogue
    assert response["response_category"] == "friendly"
    assert response["relationship_outcome"] == "friendship_positive"


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("hostile", "mean"),
        ("romantic_compliment", "romance"),
        ("romantic_invitation", "romance"),
    ],
)
def test_response_category_normalizes_known_legacy_aliases(
    alias: str, expected: str
) -> None:
    response = ai_sims_server.normalize_response(
        {
            "dialogue": "A valid response.",
            "response_category": alias,
            "relationship_outcome": "none",
        },
        [expected],
    )

    assert response["response_category"] == expected


@pytest.mark.parametrize("category", ["angry", "seductive", "social"])
def test_response_category_rejects_unknown_aliases(category: str) -> None:
    with pytest.raises(ValueError, match="invalid or unavailable"):
        ai_sims_server.normalize_response(
            {"dialogue": "A response.", "response_category": category},
            list(ai_sims_server.SOCIAL_CATEGORIES),
        )
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "friendship_category_alias_preserves or normalizes_known_legacy_aliases or rejects_unknown_aliases"
```

Expected: the live friendship case fails as `funny` is unavailable; known mean and romantic aliases fail; unknown aliases already pass.

- [ ] **Step 3: Apply the existing alias map consistently**

Add `friendship` to the existing map and apply the map after choosing either the new response field or legacy interaction field:

```python
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
raw_category = str(
    raw.get("response_category")
    or legacy_kind
    or "friendly"
)
category = legacy_categories.get(raw_category, raw_category)
```

Delete the special dialogue inference:

```python
if category == "friendship":
    category = classify_social_category(raw.get("dialogue"))
```

- [ ] **Step 4: Run the focused Sims tests**

Run the Step 2 command.

Expected: all selected tests pass.

### Task 4: Verify both boundaries and update live-test status

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

**Interfaces:**
- Consumes: passing automated evidence from Tasks 1–3
- Produces: documentation that distinguishes automated repair from pending in-game verification

- [ ] **Step 1: Run the complete Core suite and compilation**

Run:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile src/empneon/providers/llm/configured.py src/empneon/providers/llm/lmstudio.py
```

Expected: all Core tests and compilation pass.

- [ ] **Step 2: Run the complete Sims adapter suite and compilation**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/ai_sims_server.py
```

Expected: all Sims tests and compilation pass.

- [ ] **Step 3: Record the verified automated outcome**

Update both in-game documents with:

```markdown
- Automated fix verified: Core now preserves the caller's game-agnostic schema,
  LM Studio enforces it through `/v1/chat/completions`, known Sims legacy aliases
  normalize deterministically, and unknown categories remain rejected.
- Live in-game retest: pending backend/game restart.
```

- [ ] **Step 4: Check the complete uncommitted diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only the session's intended modified and new files are listed. Do not commit or push.
