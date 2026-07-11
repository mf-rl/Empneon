"""Voice profile storage — provider + voice_id + tuning params per agent."""

import json
import sqlite3
from dataclasses import dataclass, field


@dataclass
class VoiceProfile:
    agent_id: str
    provider: str | None = None     # e.g. "xtts", "kokoro", "piper", "elevenlabs"
    voice_id: str | None = None     # provider-specific voice identifier
    speed: float = 1.0              # playback speed multiplier
    pitch: float = 1.0              # pitch multiplier
    settings: dict = field(default_factory=dict)  # provider-specific extras


class VoiceProfileStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, profile: VoiceProfile) -> VoiceProfile:
        self._conn.execute(
            "INSERT INTO voice_profiles"
            "(agent_id, provider, voice_id, speed, pitch, settings)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(agent_id) DO UPDATE SET"
            " provider=excluded.provider,"
            " voice_id=excluded.voice_id,"
            " speed=excluded.speed,"
            " pitch=excluded.pitch,"
            " settings=excluded.settings",
            (
                profile.agent_id,
                profile.provider,
                profile.voice_id,
                profile.speed,
                profile.pitch,
                json.dumps(profile.settings),
            ),
        )
        self._conn.commit()
        return profile

    def get(self, agent_id: str) -> "VoiceProfile | None":
        row = self._conn.execute(
            "SELECT * FROM voice_profiles WHERE agent_id=?",
            (agent_id,),
        ).fetchone()
        return _to_profile(row) if row is not None else None

    def delete(self, agent_id: str) -> None:
        self._conn.execute(
            "DELETE FROM voice_profiles WHERE agent_id=?",
            (agent_id,),
        )
        self._conn.commit()


def _to_profile(row: sqlite3.Row) -> VoiceProfile:
    return VoiceProfile(
        agent_id=row["agent_id"],
        provider=row["provider"],
        voice_id=row["voice_id"],
        speed=row["speed"],
        pitch=row["pitch"],
        settings=json.loads(row["settings"]) if row["settings"] else {},
    )
