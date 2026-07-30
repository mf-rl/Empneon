# Empneon for Godot

Godot adapter and localhost bridge for Empneon Core. This is a small portability proof, not a
production game integration.

## Install a release

Download the `godot-vX.Y.Z` release and extract `Empneon-Godot-X.Y.Z.zip`. Install the matching
Core and Godot adapter packages included in `wheels/`:

```bash
python -m pip install wheels/*.whl
```

Open the included `portability/` project in Godot. Verify the downloaded ZIP against
`SHA256SUMS.txt` before extracting it.

## Development

```bash
python -m pip install -e ".[dev]"
ruff check src tests
mypy src
pytest
python -m empneon_godot.bridge
```

In another terminal:

```bash
godot --headless --path portability
```

The successful engine output contains `EMPNEON_GODOT_OK`.

## Current validation

The headless portability project exercises the Core adapter contract through the localhost bridge
and reports `EMPNEON_GODOT_OK` when the round trip succeeds. This proves the current minimal bridge
works in the included project; it does not establish production readiness, broad Godot-version
compatibility, or a complete gameplay integration.

## License

Licensed under the [Apache License 2.0](../../LICENSE).
