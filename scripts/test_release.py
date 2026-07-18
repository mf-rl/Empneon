import hashlib
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release  # noqa: E402


def _write(path: Path, content: str = "runtime") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fake_repo(tmp_path: Path) -> Path:
    for component, package in (
        ("core", "empneon"),
        ("adapters/thesims4", "empneon_thesims4"),
        ("adapters/godot", "empneon_godot"),
    ):
        dynamic = component == "core"
        version_line = 'dynamic = ["version"]' if dynamic else 'version = "0.3.0"'
        dependencies = "" if dynamic else 'dependencies = ["empneon>=0.3.0,<0.4"]'
        _write(
            tmp_path / component / "pyproject.toml",
            f'[project]\nname = "{package.replace("_", "-")}"\n{version_line}\n{dependencies}\n',
        )
        _write(
            tmp_path / component / "src" / package / "__init__.py",
            '__version__ = "0.3.0"\n',
        )

    _write(tmp_path / "core/dist/empneon-0.3.0-py3-none-any.whl")
    _write(tmp_path / "core/dist/empneon-0.3.0.tar.gz")
    _write(tmp_path / "adapters/thesims4/dist/empneon_thesims4-0.3.0-py3-none-any.whl")
    _write(tmp_path / "adapters/thesims4/dist/Empneon_TheSims4.ts4script")
    _write(tmp_path / "adapters/thesims4/dist/Empneon_TheSims4.package")
    _write(tmp_path / "adapters/thesims4/backend/ai_sims_server.py")
    _write(tmp_path / "adapters/thesims4/config/config.json", "{}")
    for name in ("install_mod.ps1", "run_backend.ps1", "README.md", "docs/setup.md"):
        _write(tmp_path / "adapters/thesims4" / name)

    _write(tmp_path / "adapters/godot/dist/empneon_godot-0.3.0-py3-none-any.whl")
    for name in ("main.gd", "main.tscn", "project.godot", "scenario.json"):
        _write(tmp_path / "adapters/godot/portability" / name)
    _write(tmp_path / "adapters/godot/README.md")
    return tmp_path


@pytest.mark.parametrize("component", ["core", "thesims4", "godot"])
def test_parse_release_tag(component: str) -> None:
    assert release.parse_release_tag(f"{component}-v0.3.0") == (component, "0.3.0")


@pytest.mark.parametrize("tag", ["v0.3.0", "core-0.3.0", "other-v0.3.0", "core-v0.3"])
def test_parse_release_tag_rejects_invalid_tags(tag: str) -> None:
    with pytest.raises(ValueError, match="release tag"):
        release.parse_release_tag(tag)


def test_validate_versions_rejects_mismatch(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    init = root / "adapters/godot/src/empneon_godot/__init__.py"
    init.write_text('__version__ = "0.2.0"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="0.2.0"):
        release.validate_versions(root, "godot", "0.3.0")


@pytest.mark.parametrize("component", ["core", "thesims4", "godot"])
def test_repository_versions_are_synchronized(component: str) -> None:
    release.validate_versions(ROOT, component, "0.3.0")


def test_package_sims_contains_only_runtime_files(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    _write(root / "adapters/thesims4/tests/secret.env", "TOKEN=bad")
    assets = release.package_component(root, "thesims4", "0.3.0", root / "release")
    archive = next(path for path in assets if path.suffix == ".zip")
    with ZipFile(archive) as package:
        assert set(package.namelist()) == {
            "README.md",
            "backend/ai_sims_server.py",
            "config/config.json",
            "dist/Empneon_TheSims4.package",
            "dist/Empneon_TheSims4.ts4script",
            "docs/setup.md",
            "install_mod.ps1",
            "run_backend.ps1",
            "wheels/empneon-0.3.0-py3-none-any.whl",
            "wheels/empneon_thesims4-0.3.0-py3-none-any.whl",
        }
        assert all("secret" not in name and "tests" not in name for name in package.namelist())


def test_package_godot_contains_only_runtime_files(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    assets = release.package_component(root, "godot", "0.3.0", root / "release")
    archive = next(path for path in assets if path.suffix == ".zip")
    with ZipFile(archive) as package:
        assert set(package.namelist()) == {
            "README.md",
            "portability/main.gd",
            "portability/main.tscn",
            "portability/project.godot",
            "portability/scenario.json",
            "wheels/empneon-0.3.0-py3-none-any.whl",
            "wheels/empneon_godot-0.3.0-py3-none-any.whl",
        }


def test_validate_archive_rejects_unsafe_paths(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("../secret.env", "bad")
    with pytest.raises(ValueError, match="unexpected archive members"):
        release.validate_archive(archive, {"README.md"})


def test_write_checksums_uses_sha256_and_sorted_names(tmp_path: Path) -> None:
    second = tmp_path / "b.zip"
    first = tmp_path / "a.whl"
    first.write_bytes(b"empneon")
    second.write_bytes(b"adapter")
    target = tmp_path / "SHA256SUMS.txt"
    release.write_checksums([second, first], target)
    expected = (
        f"{hashlib.sha256(first.read_bytes()).hexdigest()}  a.whl\n"
        f"{hashlib.sha256(second.read_bytes()).hexdigest()}  b.zip\n"
    )
    assert target.read_text(encoding="utf-8") == expected


def test_release_workflow_has_required_contract() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    for text in (
        "release:",
        "types: [published]",
        "workflow_dispatch:",
        "core-v*",
        "thesims4-v*",
        "godot-v*",
        "contents: read",
        "contents: write",
        "windows-2022",
        "pytest",
        "twine check",
        "python -m build",
        "scripts/release.py validate",
        "scripts/release.py package",
        "scripts/release.py notes",
        "SHA256SUMS.txt",
        "gh release create",
        "GH_REPO: ${{ github.repository }}",
        "generate-notes",
        "actions/checkout@v6",
        "actions/setup-python@v6",
        "actions/upload-artifact@v7",
        "actions/download-artifact@v8",
        "Expand-Archive",
        "run_backend.ps1 -InstallOnly",
    ):
        assert text in workflow
    for forbidden in (
        "REPOSITORY_SYNC_TOKEN",
        "PERSONAL_ACCESS_TOKEN",
        "secrets.PAT",
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
        "actions/download-artifact@v4",
    ):
        assert forbidden not in workflow
    assert """- name: Test Core
        if: matrix.component == 'core'
        working-directory: core
        run: python -m pytest tests""" in workflow
    assert """- name: Test cross-adapter contracts
        if: matrix.component != 'core'
        run: |
          python -m pip install -e adapters/thesims4 -e adapters/godot
          python -m pytest tests""" in workflow
    assert (
        "python -m twine check adapters/${{ matrix.component }}/dist/*.whl "
        "adapters/${{ matrix.component }}/dist/*.tar.gz"
    ) in workflow


def test_monorepo_ci_checks_release_support() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "scripts/release.py scripts/test_release.py" in workflow
    assert "pytest scripts/test_release.py" in workflow


def test_release_documentation_matches_artifacts() -> None:
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sims_readme = (ROOT / "adapters/thesims4/README.md").read_text(encoding="utf-8")
    sims_setup = (ROOT / "adapters/thesims4/docs/setup.md").read_text(encoding="utf-8")
    sims_runner = (ROOT / "adapters/thesims4/run_backend.ps1").read_text(encoding="utf-8")
    godot_readme = (ROOT / "adapters/godot/README.md").read_text(encoding="utf-8")

    for tag in ("core-vX.Y.Z", "thesims4-vX.Y.Z", "godot-vX.Y.Z"):
        assert tag in root_readme
    assert "pip install" in root_readme
    assert "SHA256SUMS.txt" in root_readme
    assert "Empneon-TheSims4-X.Y.Z.zip" in sims_readme
    assert "creates a local `.venv`" in sims_readme
    assert "pip install (Get-ChildItem .\\wheels\\*.whl)" not in sims_readme
    assert "Empneon_TheSims4.ts4script" in sims_setup
    assert "prebuilt" in sims_setup.lower()
    assert "creates a local `.venv`" in sims_setup
    assert "pip install (Get-ChildItem .\\wheels\\*.whl)" not in sims_setup
    for text in (
        "param([switch]$InstallOnly)",
        'Join-Path $PSScriptRoot ".venv\\Scripts\\python.exe"',
        'Join-Path $PSScriptRoot "wheels"',
        "-m pip install",
        "import empneon, empneon_thesims4",
    ):
        assert text in sims_runner
    assert "..\\..\\core\\src" not in sims_runner
    assert "Empneon-Godot-X.Y.Z.zip" in godot_readme
    assert "wheels/" in godot_readme

    sims_notes = release.release_notes("thesims4", "0.3.0")
    assert "automatically installs the bundled wheels" in sims_notes
