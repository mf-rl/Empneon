import pytest

from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.identity.voice import VoiceProfile, VoiceProfileStore
from empneon.db.connection import open_db


@pytest.fixture
def stores() -> tuple[AgentStore, VoiceProfileStore]:
    conn = open_db(":memory:")
    return AgentStore(conn), VoiceProfileStore(conn)


def _agent(stores: tuple[AgentStore, VoiceProfileStore]) -> Agent:
    a = Agent.new("Alice")
    stores[0].create(a)
    return a


def test_set_and_get(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    profile = VoiceProfile(a.id, provider="xtts", voice_id="en_female_01", speed=1.1, pitch=0.95)
    stores[1].set(profile)
    fetched = stores[1].get(a.id)
    assert fetched is not None
    assert fetched.provider == "xtts"
    assert fetched.voice_id == "en_female_01"
    assert fetched.speed == pytest.approx(1.1)
    assert fetched.pitch == pytest.approx(0.95)


def test_get_missing_returns_none(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    assert stores[1].get(a.id) is None


def test_upsert_updates_existing(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    stores[1].set(VoiceProfile(a.id, provider="piper", voice_id="v1"))
    stores[1].set(VoiceProfile(a.id, provider="kokoro", voice_id="v2", speed=1.5))
    fetched = stores[1].get(a.id)
    assert fetched is not None
    assert fetched.provider == "kokoro"
    assert fetched.voice_id == "v2"
    assert fetched.speed == pytest.approx(1.5)


def test_settings_roundtrip(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    settings = {"language": "en", "emotion": "neutral", "sample_rate": 22050}
    stores[1].set(VoiceProfile(a.id, settings=settings))
    fetched = stores[1].get(a.id)
    assert fetched is not None
    assert fetched.settings == settings


def test_empty_settings_default(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    stores[1].set(VoiceProfile(a.id))
    fetched = stores[1].get(a.id)
    assert fetched is not None
    assert fetched.settings == {}


def test_null_provider_and_voice_id(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    stores[1].set(VoiceProfile(a.id))
    fetched = stores[1].get(a.id)
    assert fetched is not None
    assert fetched.provider is None
    assert fetched.voice_id is None


def test_delete_profile(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    stores[1].set(VoiceProfile(a.id, provider="piper"))
    stores[1].delete(a.id)
    assert stores[1].get(a.id) is None


def test_cascade_delete_agent(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    stores[1].set(VoiceProfile(a.id, provider="xtts"))
    stores[0].delete(a.id)
    assert stores[1].get(a.id) is None


def test_profiles_are_per_agent(stores: tuple[AgentStore, VoiceProfileStore]) -> None:
    a = _agent(stores)
    b = Agent.new("Bob")
    stores[0].create(b)
    stores[1].set(VoiceProfile(a.id, provider="xtts", voice_id="alice_voice"))
    stores[1].set(VoiceProfile(b.id, provider="kokoro", voice_id="bob_voice"))
    assert stores[1].get(a.id).voice_id == "alice_voice"  # type: ignore[union-attr]
    assert stores[1].get(b.id).voice_id == "bob_voice"  # type: ignore[union-attr]
