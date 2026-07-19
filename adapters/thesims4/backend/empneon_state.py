import contextlib
import dataclasses
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from empneon.db.connection import open_db


@dataclass(frozen=True)
class MigrationStatus:
    active_path: str
    sources: tuple[str, ...] = ()
    backups: tuple[str, ...] = ()
    completed: bool = True
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def prepare_database(target: str, legacy_core: str, legacy_adapter: str) -> MigrationStatus:
    destination = Path(target).resolve()
    legacy_paths = tuple(Path(value).resolve() for value in (legacy_core, legacy_adapter))
    sources = tuple(str(path) for path in legacy_paths if path.exists() and path != destination)
    backups: list[str] = []
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        core_source = legacy_paths[0]
        if not destination.exists() and core_source.exists() and core_source != destination:
            with contextlib.closing(
                sqlite3.connect(core_source.as_uri() + "?mode=ro", uri=True)
            ) as source, contextlib.closing(sqlite3.connect(destination)) as output:
                source.backup(output)
            backup = _backup(core_source)
            backups.append(str(backup))
        with open_db(destination):
            pass
        return MigrationStatus(str(destination), sources, tuple(backups))
    except Exception as exc:
        return MigrationStatus(
            str(destination), sources, tuple(backups), completed=False, error=str(exc)
        )


def open_memory(target: str) -> sqlite3.Connection:
    return open_db(target)


def _backup(source: Path) -> Path:
    backup = source.with_suffix(source.suffix + ".pre-core-memory.bak")
    if not backup.exists():
        shutil.copy2(source, backup)
    return backup
