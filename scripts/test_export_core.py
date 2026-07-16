from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    output = ROOT / ".core-publication-test"
    if output.exists():
        raise SystemExit(f"remove stale test directory first: {output}")
    try:
        subprocess.run(
            [sys.executable, "scripts/export_core.py", "--output", str(output)],
            cwd=ROOT,
            check=True,
        )
        assert (output / "src/empneon/core/runtime.py").is_file()
        assert (output / "docs/api.md").is_file()
        assert not (output / "poc/ai_sims_memory.sqlite3").exists()
        assert not (output / "docs/business-model.md").exists()
        assert not (output / "docs/design-partners.md").exists()
        assert not (output / "docs/roadmap.md").exists()
        assert not (output / "CLAUDE.md").exists()
        readme = (output / "README.md").read_text(encoding="utf-8")
        assert "docs/business-model.md" not in readme
        assert "docs/design-partners.md" not in readme
    finally:
        shutil.rmtree(output, ignore_errors=True)


if __name__ == "__main__":
    main()
