"""Export one safe, tracked product snapshot from the private monorepo."""

from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".github" / "publications.toml"
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
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [path.decode() for path in result.stdout.split(b"\0") if path]


def selected_files(product_name: str) -> tuple[str, list[tuple[str, str]]]:
    with MANIFEST.open("rb") as file:
        config = tomllib.load(file)
    products = config["products"]
    if product_name not in products:
        raise SystemExit(f"unknown product: {product_name}")
    product = products[product_name]
    source = str(product["source"]).rstrip("/")
    prefix = source + "/"
    common = config.get("common", [])
    selected = []
    for path in tracked_files():
        if path.startswith(prefix):
            selected.append((path, path[len(prefix) :]))
        elif any(fnmatch.fnmatchcase(path, pattern) for pattern in common):
            selected.append((path, path))
    return str(product["repository"]), selected


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


def export(product_name: str, output: Path) -> None:
    repository, files = selected_files(product_name)
    if not files:
        raise SystemExit(f"no tracked files selected for {product_name}")
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    destinations: set[Path] = set()
    for source_path, destination_path in files:
        source = validate(source_path)
        destination_relative = Path(destination_path)
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
    parser.add_argument("--product", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.product, args.output.resolve())


if __name__ == "__main__":
    main()
