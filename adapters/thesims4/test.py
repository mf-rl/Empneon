import json
import os
import urllib.error
import urllib.request


payload = {
    "speaker": {
        "id": "bella-goth",
        "name": "Bella Goth",
        "traits": ["romantic", "family-oriented", "mysterious"],
        "current_mood": "tense",
        "career": "secret agent",
        "skills": {"charisma": 7},
    },
    "listener": {
        "id": "player-sim",
        "name": "Player Sim",
        "traits": ["loyal"],
        "current_mood": "curious",
    },
    "relationship": {
        "friendship": 45,
        "romance": 20,
        "trust": 40,
        "resentment": 15,
    },
    "message": "Why have you been avoiding me?",
}

headers = {"Content-Type": "application/json"}
api_token = os.environ.get("AI_SIM_API_TOKEN")
if api_token:
    headers["X-Empneon-Token"] = api_token
request = urllib.request.Request(
    os.environ.get("AI_SIM_TEST_URL", "http://127.0.0.1:8765/chat"),
    data=json.dumps(payload).encode("utf-8"),
    headers=headers,
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=120) as response:
        print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
except urllib.error.HTTPError as exc:
    print(exc.read().decode("utf-8", "replace"))
    raise SystemExit(1)
