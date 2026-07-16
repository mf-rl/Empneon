# Empneon for Godot

Godot adapter and localhost bridge for Empneon Core.

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

Licensed under the [Apache License 2.0](LICENSE).
