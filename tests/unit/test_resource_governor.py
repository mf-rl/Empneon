import pytest

from empneon.core.scheduler.resources import (
    ResourceBudget,
    ResourceEstimate,
    ResourceGovernor,
    ResourceLimitExceeded,
    ResourceSnapshot,
)


def test_reserves_and_releases_resources() -> None:
    governor = ResourceGovernor(ResourceBudget(1_000, 500, 1))

    with governor.reserve(ResourceEstimate(ram_mb=200, vram_mb=100)):
        assert governor.snapshot == ResourceSnapshot(200, 100, 1)

    assert governor.snapshot == ResourceSnapshot(0, 0, 0)


def test_rejects_request_over_vram_budget() -> None:
    governor = ResourceGovernor(ResourceBudget(1_000, 500, 1))

    with pytest.raises(ResourceLimitExceeded):
        with governor.reserve(ResourceEstimate(vram_mb=501)):
            pass


def test_rejects_concurrent_request_and_keeps_outer_reservation() -> None:
    governor = ResourceGovernor(ResourceBudget(1_000, 500, 1))

    with governor.reserve(ResourceEstimate(ram_mb=100)):
        with pytest.raises(ResourceLimitExceeded):
            with governor.reserve(ResourceEstimate(ram_mb=100)):
                pass
        assert governor.snapshot == ResourceSnapshot(100, 0, 1)


def test_releases_after_request_failure() -> None:
    governor = ResourceGovernor(ResourceBudget(1_000, 500, 1))

    with pytest.raises(RuntimeError):
        with governor.reserve(ResourceEstimate(ram_mb=100)):
            raise RuntimeError("provider failed")

    assert governor.snapshot == ResourceSnapshot(0, 0, 0)
