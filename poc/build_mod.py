from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from zipfile import ZIP_STORED, ZipFile


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "ts4script" / "ai_sims_agent.py"
TARGET = ROOT / "dist" / "AI_Sims_Agent.ts4script"


def compile_pyc(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "import py_compile, sys; "
        "py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)"
    )
    subprocess.run(["py", "-3.7", "-c", code, str(source), str(target)], check=True)


def main():
    if not shutil.which("py"):
        raise SystemExit("Python launcher not found. Install Python 3.7 and rerun.")

    TARGET.parent.mkdir(exist_ok=True)
    prefix = "ai-sims-{}-".format(uuid.uuid4().hex)
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
    finally:
        for _, pyc, _ in files:
            try:
                pyc.unlink()
            except FileNotFoundError:
                pass
    print("built {}".format(TARGET))


if __name__ == "__main__":
    main()
