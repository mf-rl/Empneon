"""Export the safe, tracked EmpneonCore release snapshot."""

from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".github" / "core-publication.toml"
SENSITIVE_SUFFIXES = {
    ".db",
    ".env",
    ".key",
    ".log",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}
SENSITIVE_NAMES = {"credentials", "credentials.json", "secrets.json"}
SECRET_PATTERNS = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    rb"|gh[pousr]_[A-Za-z0-9]{20,}"
    rb"|sk-[A-Za-z0-9_-]{20,}"
    rb"|AIza[0-9A-Za-z_-]{20,}"
    rb"|AKIA[0-9A-Z]{16}"
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [path.decode() for path in result.stdout.split(b"\0") if path]


def selected_files() -> tuple[str, list[str], dict[str, str]]:
    with MANIFEST.open("rb") as file:
        config = tomllib.load(file)
    includes = config["include"]
    excludes = config.get("exclude", [])
    selected = [
        path
        for path in tracked_files()
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in includes)
        and not any(fnmatch.fnmatchcase(path, pattern) for pattern in excludes)
    ]
    return str(config["repository"]), selected, dict(config.get("rename", {}))


def validate(path: str) -> Path:
    relative = Path(path)
    unresolved = ROOT / relative
    source = unresolved.resolve()
    if relative.is_absolute() or ROOT not in source.parents:
        raise SystemExit(f"unsafe publication path: {path}")
    if unresolved.is_symlink():
        raise SystemExit(f"symlinks cannot be published: {path}")
    if relative.name.lower() in SENSITIVE_NAMES or relative.suffix.lower() in SENSITIVE_SUFFIXES:
        raise SystemExit(f"sensitive file cannot be published: {path}")
    if SECRET_PATTERNS.search(source.read_bytes()):
        raise SystemExit(f"possible secret cannot be published: {path}")
    return source


def export(output: Path) -> None:
    repository, files, renames = selected_files()
    if not files:
        raise SystemExit("no tracked files selected for publication")
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    destinations: set[Path] = set()
    for path in files:
        source = validate(path)
        destination_relative = Path(renames.get(path, path))
        destination = (output / destination_relative).resolve()
        if destination_relative.is_absolute() or output not in destination.parents:
            raise SystemExit(f"unsafe destination path: {destination_relative}")
        if destination in destinations:
            raise SystemExit(f"duplicate destination path: {destination_relative}")
        destinations.add(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    print(f"Exported {len(files)} files for {repository}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.output.resolve())


if __name__ == "__main__":
    main()
