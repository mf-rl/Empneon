import shutil
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "ts4script" / "ai_sims_agent.py"
TARGET = ROOT / "dist" / "Empneon_TheSims4.ts4script"
TUNING_SOURCE = ROOT / "tuning" / "empneon_social_interaction.xml"
TUNING_TARGET = ROOT / "dist" / "Empneon_TheSims4.package"
INTERACTION_TUNING_TYPE = 0xE882D22F
EMPNEON_SOCIAL_INTERACTION_ID = 0xEAA1100000000001


def compile_pyc(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "import py_compile, sys; "
        "py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)"
    )
    subprocess.run(["py", "-3.7", "-c", code, str(source), str(target)], check=True)


def build_tuning_package(source, target):
    data = source.read_bytes()
    resource_offset = 96
    index_offset = resource_offset + len(data)
    index = struct.pack(
        "<IIIIIIII",
        INTERACTION_TUNING_TYPE,
        0,
        EMPNEON_SOCIAL_INTERACTION_ID >> 32,
        EMPNEON_SOCIAL_INTERACTION_ID & 0xFFFFFFFF,
        resource_offset,
        len(data) | 0x80000000,
        len(data),
        0x00010000,
    )
    header = bytearray(96)
    struct.pack_into("<4sII", header, 0, b"DBPF", 2, 1)
    struct.pack_into("<III", header, 36, 1, index_offset, 4 + len(index))
    struct.pack_into("<IQ", header, 60, 3, index_offset)
    target.write_bytes(header + data + struct.pack("<I", 0) + index)


def main():
    if not shutil.which("py"):
        raise SystemExit("Python launcher not found. Install Python 3.7 and rerun.")

    TARGET.parent.mkdir(exist_ok=True)
    prefix = f"empneon-sims4-{uuid.uuid4().hex}-"
    temp = Path(tempfile.gettempdir())
    files = [
        (SOURCE, temp / (prefix + "ai_sims_agent.pyc"), "ai_sims_agent.pyc"),
    ]
    try:
        for source, pyc, _ in files:
            compile_pyc(source, pyc)

        with ZipFile(str(TARGET), "w", ZIP_STORED) as package:
            for _, pyc, name in files:
                package.write(str(pyc), name)
        build_tuning_package(TUNING_SOURCE, TUNING_TARGET)
    finally:
        for _, pyc, _ in files:
            try:
                pyc.unlink()
            except FileNotFoundError:
                pass
    print(f"built {TARGET} and {TUNING_TARGET}")


if __name__ == "__main__":
    main()
