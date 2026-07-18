# Empneon for Godot

Godot adapter and localhost bridge for Empneon Core.

## Install a release

Download and extract `Empneon-Godot-X.Y.Z.zip` from GitHub Releases. Install the matching Core
and Godot adapter packages included in `wheels/`:

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

## License

Licensed under the [Apache License 2.0](../../LICENSE).
