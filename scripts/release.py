"""Validate and assemble Empneon GitHub Release assets."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import tomllib

COMPONENTS = {
    "core": (Path("core"), "empneon", "empneon"),
    "thesims4": (Path("adapters/thesims4"), "empneon_thesims4", "empneon_thesims4"),
    "godot": (Path("adapters/godot"), "empneon_godot", "empneon_godot"),
}
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
TAG_RE = re.compile(r"^(core|thesims4|godot)-v(\d+\.\d+\.\d+)$")
UNIFIED_TAG_RE = re.compile(r"^v((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))$")
SIMS_BACKEND_FILES = (
    "agent_manager.py",
    "ai_sims_server.py",
    "cognition.py",
    "config.py",
    "db.py",
    "empneon_state.py",
    "server.py",
)


def parse_release_tag(tag: str) -> tuple[str, str]:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError(f"invalid release tag: {tag}")
    return match.group(1), match.group(2)


def parse_unified_release_tag(tag: str) -> str:
    match = UNIFIED_TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError(f"invalid unified release tag: {tag}")
    return match.group(1)


def _project(root: Path, component: str) -> tuple[Path, str, str, dict[str, object]]:
    try:
        relative, package, distribution = COMPONENTS[component]
    except KeyError as exc:
        raise ValueError(f"unsupported component: {component}") from exc
    path = root / relative
    with (path / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)["project"]
    return path, package, distribution, metadata


def _import_version(init_file: Path) -> str:
    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']',
        init_file.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise ValueError(f"missing __version__ in {init_file}")
    return match.group(1)


def validate_versions(root: Path, component: str, version: str) -> None:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid release version: {version}")
    path, package, _, metadata = _project(root, component)
    imported = _import_version(path / "src" / package / "__init__.py")
    if imported != version:
        raise ValueError(f"{component} imports version {imported}, expected {version}")

    declared = metadata.get("version")
    if declared is not None and declared != version:
        raise ValueError(f"{component} metadata version {declared}, expected {version}")
    if component == "core" and "version" not in metadata.get("dynamic", []):
        raise ValueError("core metadata must declare a dynamic version")
    if component != "core":
        major, minor, _ = (int(part) for part in version.split("."))
        requirement = f"empneon>={version},<{major}.{minor + 1}"
        if requirement not in metadata.get("dependencies", []):
            raise ValueError(f"{component} must depend on {requirement}")


def _single(directory: Path, pattern: str) -> Path:
    matches = list(directory.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"expected one {pattern} in {directory}, found {len(matches)}")
    return matches[0]


def validate_archive(archive: Path, expected_members: set[str]) -> None:
    with ZipFile(archive) as package:
        members = package.namelist()
    if len(members) != len(set(members)) or set(members) != expected_members:
        raise ValueError(f"unexpected archive members in {archive.name}: {sorted(members)}")


def write_checksums(files: list[Path], target: Path) -> None:
    lines = []
    for path in sorted(files, key=lambda item: item.name):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}\n")
    target.write_text("".join(lines), encoding="utf-8", newline="\n")


def _zip_runtime(archive: Path, files: dict[str, Path]) -> None:
    missing = [str(source) for source in files.values() if not source.is_file()]
    if missing:
        raise ValueError(f"missing runtime files: {', '.join(missing)}")
    with ZipFile(archive, "w", ZIP_DEFLATED) as package:
        for destination, source in sorted(files.items()):
            package.write(source, destination)
    validate_archive(archive, set(files))


def package_component(root: Path, component: str, version: str, output: Path) -> list[Path]:
    validate_versions(root, component, version)
    output.mkdir(parents=True, exist_ok=True)
    path, _, distribution, _ = _project(root, component)
    core_wheel = _single(root / "core/dist", f"empneon-{version}-*.whl")
    assets: list[Path]

    if component == "core":
        source_distribution = _single(root / "core/dist", f"empneon-{version}.tar.gz")
        assets = []
        for source in (core_wheel, source_distribution):
            target = output / source.name
            shutil.copy2(source, target)
            assets.append(target)
    else:
        adapter_wheel = _single(path / "dist", f"{distribution}-{version}-*.whl")
        runtime: dict[str, Path] = {
            "README.md": path / "README.md",
            f"wheels/{core_wheel.name}": core_wheel,
            f"wheels/{adapter_wheel.name}": adapter_wheel,
        }
        if component == "thesims4":
            runtime.update(
                {
                    "backend/ai_sims_server.py": path / "backend/ai_sims_server.py",
                    "backend/empneon_state.py": path / "backend/empneon_state.py",
                    "config/config.json": path / "config/config.json",
                    "dist/Empneon_TheSims4.package": path / "dist/Empneon_TheSims4.package",
                    "dist/Empneon_TheSims4.ts4script": path
                    / "dist/Empneon_TheSims4.ts4script",
                    "docs/setup.md": path / "docs/setup.md",
                    "docs/in-game-core-feature-test-plan.md": path
                    / "docs/in-game-core-feature-test-plan.md",
                    "install_mod.ps1": path / "install_mod.ps1",
                    "run_backend.ps1": path / "run_backend.ps1",
                }
            )
            archive = output / f"Empneon-TheSims4-{version}.zip"
        else:
            for name in ("main.gd", "main.tscn", "project.godot", "scenario.json"):
                runtime[f"portability/{name}"] = path / "portability" / name
            archive = output / f"Empneon-Godot-{version}.zip"
        _zip_runtime(archive, runtime)
        assets = [archive]

    checksums = output / "SHA256SUMS.txt"
    write_checksums(assets, checksums)
    return [*assets, checksums]


def package_unified(root: Path, version: str, output: Path) -> list[Path]:
    for component in COMPONENTS:
        validate_versions(root, component, version)

    output.mkdir(parents=True, exist_ok=True)
    core_wheel = _single(root / "core/dist", f"empneon-{version}-*.whl")
    sims_wheel = _single(
        root / "adapters/thesims4/dist",
        f"empneon_thesims4-{version}-*.whl",
    )
    sims = root / "adapters/thesims4"

    core_files = {
        "LICENSE": root / "LICENSE",
        "README.md": root / "core/README.md",
        f"wheels/{core_wheel.name}": core_wheel,
    }
    sims_files = {
        "LICENSE": root / "LICENSE",
        "README.md": sims / "README.md",
        "config/config.json": sims / "config/config.json",
        "dist/Empneon_TheSims4.package": sims / "dist/Empneon_TheSims4.package",
        "dist/Empneon_TheSims4.ts4script": sims / "dist/Empneon_TheSims4.ts4script",
        "install_mod.ps1": sims / "install_mod.ps1",
        "run_backend.ps1": sims / "run_backend.ps1",
        f"wheels/{core_wheel.name}": core_wheel,
        f"wheels/{sims_wheel.name}": sims_wheel,
        **{f"backend/{name}": sims / "backend" / name for name in SIMS_BACKEND_FILES},
    }
    archives = [
        output / f"empneon-core-v{version}.zip",
        output / f"empneon-thesims4-adapter-v{version}.zip",
    ]
    _zip_runtime(archives[0], core_files)
    _zip_runtime(archives[1], sims_files)
    return archives


def release_notes(component: str, version: str) -> str:
    if component == "core":
        instructions = "Install the wheel with `python -m pip install ./empneon-*.whl`."
    elif component == "thesims4":
        instructions = (
            "Extract the ZIP, then run `install_mod.ps1` and `run_backend.ps1`. "
            "The backend script automatically installs the bundled wheels into a local `.venv`."
        )
    elif component == "godot":
        instructions = (
            "Extract the ZIP, install both files in `wheels/`, and open the `portability` "
            "project in Godot."
        )
    else:
        raise ValueError(f"unsupported component: {component}")
    return f"# Empneon {component} {version}\n\n{instructions}\n\nVerify assets with `SHA256SUMS.txt`.\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("validate", "package", "notes", "package-unified"),
    )
    parser.add_argument("target")
    parser.add_argument("version", nargs="?")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("release"))
    args = parser.parse_args()

    if args.command == "package-unified":
        if args.version is not None:
            parser.error("package-unified accepts VERSION without a component")
        package_unified(args.root, args.target, args.output)
    else:
        if args.target not in COMPONENTS or args.version is None:
            parser.error(f"{args.command} requires COMPONENT VERSION")
        component = args.target
        version = args.version
        if args.command == "validate":
            validate_versions(args.root, component, version)
        elif args.command == "package":
            package_component(args.root, component, version, args.output)
        else:
            validate_versions(args.root, component, version)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                release_notes(component, version),
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
