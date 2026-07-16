from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export(product: str) -> Path:
    output = ROOT / f".publication-test-{product}"
    if output.exists():
        raise SystemExit(f"remove stale test directory first: {output}")
    subprocess.run(
        [
            sys.executable,
            "scripts/export_product.py",
            "--product",
            product,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    return output


def main() -> None:
    outputs: list[Path] = []
    try:
        core = export("core")
        outputs.append(core)
        assert (core / "src/empneon/core/runtime.py").is_file()
        assert (core / "src/empneon/core/ports.py").is_file()
        assert not (core / "src/empneon/adapters").exists()
        assert not (core / "thesims4").exists()

        sims = export("thesims4")
        outputs.append(sims)
        assert (sims / "src/empneon_thesims4/adapter.py").is_file()
        assert (sims / "ts4script/ai_sims_agent.py").is_file()
        assert not (sims / "core").exists()

        godot = export("godot")
        outputs.append(godot)
        assert (godot / "src/empneon_godot/bridge.py").is_file()
        assert (godot / "portability/project.godot").is_file()
        assert not (godot / "core").exists()

        for output in outputs:
            assert (output / "LICENSE").is_file()
            assert (output / ".github/workflows/ci.yml").is_file()
    finally:
        for output in outputs:
            shutil.rmtree(output, ignore_errors=True)


if __name__ == "__main__":
    main()
