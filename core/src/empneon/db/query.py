"""Shared query-argument validation for SQLite-backed stores."""


def validate_limit(limit: int | None) -> None:
    """Reject non-positive limits; SQLite treats a negative LIMIT as unlimited."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
