# Unified Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach runnable Core and The Sims 4 ZIPs to a published `vX.Y.Z` GitHub release and
publish the matching Empneon Core wheel and source distribution to PyPI.

**Architecture:** Extend the existing tested `scripts/release.py` packager with an explicit
unified-archive function and CLI command. A new release-published workflow builds once, smoke-tests
the two ZIPs, uploads them to the triggering GitHub release, and passes the same Core distributions
to a separate OIDC-only PyPI job.

**Tech Stack:** Python 3.11, Python 3.7 for Sims bytecode, `zipfile`, Pytest, PowerShell, GitHub
Actions, GitHub CLI, PyPI Trusted Publishing.

## Global Constraints

- Unified release tags must match `vX.Y.Z` exactly.
- Generate only `empneon-core-vX.Y.Z.zip` and
  `empneon-thesims4-adapter-vX.Y.Z.zip`; do not generate a Godot ZIP.
- Keep `.github/workflows/release.yml` and all existing independent-release commands working.
- Publish only Empneon Core to PyPI.
- Use GitHub OIDC Trusted Publishing through the protected `pypi` environment; add no API-token
  secret.
- Include files through explicit archive mappings only; never recursively package runtime
  directories.
- The Sims ZIP must remain directly installable and runnable with its bundled wheels and scripts.
- No contributor or AI attribution may be added to commits.

---

### Task 1: Add tested unified archive packaging

**Files:**

- Modify: `scripts/test_release.py`
- Modify: `scripts/release.py`

**Interfaces:**

- Consumes: existing `validate_versions()`, `_single()`, `_zip_runtime()`, and the built artifacts
  under `core/dist` and `adapters/thesims4/dist`
- Produces: `parse_unified_release_tag(tag: str) -> str` and
  `package_unified(root: Path, version: str, output: Path) -> list[Path]`

- [ ] **Step 1: Expand the fake repository with the unified runtime boundary**

In `_fake_repo()`, create `LICENSE`, `core/README.md`, and all seven backend files:

```python
_write(tmp_path / "LICENSE", "Apache License 2.0")
_write(tmp_path / "core/README.md", "# Empneon Core")
for name in (
    "agent_manager.py",
    "ai_sims_server.py",
    "cognition.py",
    "config.py",
    "db.py",
    "empneon_state.py",
    "server.py",
):
    _write(tmp_path / "adapters/thesims4/backend" / name)
```

Retain the existing adapter README, configuration, scripts, wheels, and game artifacts.

- [ ] **Step 2: Write failing unified tag tests**

Add:

```python
def test_parse_unified_release_tag() -> None:
    assert release.parse_unified_release_tag("v0.4.0") == "0.4.0"


@pytest.mark.parametrize(
    "tag",
    ["0.4.0", "core-v0.4.0", "v0.4", "v01.4.0", "v0.4.0-rc1"],
)
def test_parse_unified_release_tag_rejects_invalid_tags(tag: str) -> None:
    with pytest.raises(ValueError, match="unified release tag"):
        release.parse_unified_release_tag(tag)
```

- [ ] **Step 3: Write the failing exact-archive test**

Add one test that calls `package_unified()` and asserts both filenames and complete member sets:

```python
def test_package_unified_contains_only_runnable_files(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path)
    _write(root / "adapters/thesims4/backend/private.sqlite3", "secret")
    _write(root / "adapters/godot/dist/empneon-godot.zip")

    assets = release.package_unified(root, "0.4.0", root / "release")

    assert [path.name for path in assets] == [
        "empneon-core-v0.4.0.zip",
        "empneon-thesims4-adapter-v0.4.0.zip",
    ]
    with ZipFile(assets[0]) as package:
        assert set(package.namelist()) == {
            "LICENSE",
            "README.md",
            "wheels/empneon-0.4.0-py3-none-any.whl",
        }
    with ZipFile(assets[1]) as package:
        assert set(package.namelist()) == {
            "LICENSE",
            "README.md",
            "backend/agent_manager.py",
            "backend/ai_sims_server.py",
            "backend/cognition.py",
            "backend/config.py",
            "backend/db.py",
            "backend/empneon_state.py",
            "backend/server.py",
            "config/config.json",
            "dist/Empneon_TheSims4.package",
            "dist/Empneon_TheSims4.ts4script",
            "install_mod.ps1",
            "run_backend.ps1",
            "wheels/empneon-0.4.0-py3-none-any.whl",
            "wheels/empneon_thesims4-0.4.0-py3-none-any.whl",
        }
```

- [ ] **Step 4: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py `
  -k "unified_release_tag or package_unified"
```

Expected: failures because `parse_unified_release_tag` and `package_unified` do not exist.

- [ ] **Step 5: Implement strict unified tag parsing**

In `scripts/release.py`, add:

```python
UNIFIED_TAG_RE = re.compile(r"^v((0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))$")


def parse_unified_release_tag(tag: str) -> str:
    match = UNIFIED_TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError(f"invalid unified release tag: {tag}")
    return match.group(1)
```

- [ ] **Step 6: Implement explicit unified ZIP mappings**

Add:

```python
SIMS_BACKEND_FILES = (
    "agent_manager.py",
    "ai_sims_server.py",
    "cognition.py",
    "config.py",
    "db.py",
    "empneon_state.py",
    "server.py",
)


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
        "dist/Empneon_TheSims4.ts4script": sims
        / "dist/Empneon_TheSims4.ts4script",
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
```

- [ ] **Step 7: Add a backward-compatible CLI command**

Keep the existing positional syntax for `validate`, `package`, and `notes`. Add
`package-unified` as a command whose second positional argument is the version:

```python
parser.add_argument(
    "command",
    choices=("validate", "package", "notes", "package-unified"),
)
parser.add_argument("target")
parser.add_argument("version", nargs="?")
```

Dispatch with:

```python
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
```

The new invocation is:

```powershell
py -3.12 scripts/release.py package-unified 0.4.0 --output release/unified
```

- [ ] **Step 8: Run focused and full release tests**

Run:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py `
  -k "unified_release_tag or package_unified"
py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py
```

Expected: all focused and all release tests pass.

- [ ] **Step 9: Run static checks**

Run:

```powershell
py -3.12 -m ruff check scripts/release.py scripts/test_release.py
py -3.12 -m py_compile scripts/release.py scripts/test_release.py
git diff --check
```

Expected: all commands exit `0`.

- [ ] **Step 10: Commit**

```powershell
git add -- scripts/release.py scripts/test_release.py
git commit -m "feat(release): package unified runtime archives"
```

---

### Task 2: Add the release-published GitHub and PyPI workflow

**Files:**

- Create: `.github/workflows/unified-release.yml`
- Modify: `scripts/test_release.py`

**Interfaces:**

- Consumes: `parse_unified_release_tag()`, the existing component validation CLI, and
  `package-unified VERSION`
- Produces: GitHub release assets `empneon-core-vX.Y.Z.zip` and
  `empneon-thesims4-adapter-vX.Y.Z.zip`, plus PyPI distributions for `empneon`

- [ ] **Step 1: Write a failing workflow-contract test**

Add:

```python
def test_unified_release_workflow_has_required_contract() -> None:
    workflow = (ROOT / ".github/workflows/unified-release.yml").read_text(encoding="utf-8")

    for text in (
        "name: Unified release",
        "release:",
        "types: [published]",
        "windows-2022",
        "package-unified",
        "empneon-core-v",
        "empneon-thesims4-adapter-v",
        "run_backend.ps1 -InstallOnly",
        "gh release upload",
        "--clobber",
        "environment: pypi",
        "id-token: write",
        "pypa/gh-action-pypi-publish@release/v1",
        "actions/checkout@v6",
        "actions/setup-python@v6",
        "actions/upload-artifact@v7",
        "actions/download-artifact@v8",
    ):
        assert text in workflow
    for forbidden in (
        "workflow_dispatch:",
        "godot-v",
        "empneon-godot",
        "PYPI_API_TOKEN",
        "secrets.PYPI",
        "gh release create",
    ):
        assert forbidden not in workflow
```

Also assert the job ordering and least privilege:

```python
assert "attach-release-assets:\n    needs: build" in workflow
assert "publish-core:\n    needs: [build, attach-release-assets]" in workflow
assert "packages-dir: dist/" in workflow
```

- [ ] **Step 2: Run the workflow test and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider `
  scripts/test_release.py::test_unified_release_workflow_has_required_contract
```

Expected: failure because `.github/workflows/unified-release.yml` does not exist.

- [ ] **Step 3: Create the workflow trigger and build job**

Create `.github/workflows/unified-release.yml` with:

```yaml
name: Unified release

on:
  release:
    types: [published]

permissions:
  contents: read

jobs:
  build:
    runs-on: windows-2022
    outputs:
      version: ${{ steps.version.outputs.version }}
    steps:
      - uses: actions/checkout@v6
      - name: Set up Python 3.7 for The Sims 4
        uses: actions/setup-python@v6
        with:
          python-version: "3.7"
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
      - name: Install build tools
        run: python -m pip install --upgrade build pytest twine
      - id: version
        name: Validate unified release tag
        shell: pwsh
        env:
          RELEASE_TAG: ${{ github.event.release.tag_name }}
        run: |
          $version = py -3.11 -c "import os; from scripts.release import parse_unified_release_tag; print(parse_unified_release_tag(os.environ['RELEASE_TAG']))"
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          "version=$version" >> $env:GITHUB_OUTPUT
      - name: Validate repository versions
        shell: pwsh
        run: |
          py -3.11 scripts/release.py validate core ${{ steps.version.outputs.version }}
          py -3.11 scripts/release.py validate thesims4 ${{ steps.version.outputs.version }}
          py -3.11 scripts/release.py validate godot ${{ steps.version.outputs.version }}
      - name: Test release packaging
        run: py -3.11 -m pytest -q scripts/test_release.py
      - name: Build Core
        working-directory: core
        run: py -3.11 -m build
      - name: Build The Sims 4 adapter
        working-directory: adapters/thesims4
        run: py -3.11 -m build
      - name: Validate Python distributions
        shell: pwsh
        run: |
          py -3.11 -m twine check core/dist/*
          py -3.11 -m twine check adapters/thesims4/dist/*.whl adapters/thesims4/dist/*.tar.gz
      - name: Build The Sims 4 mod
        run: py -3.11 adapters/thesims4/build_mod.py
      - name: Package unified archives
        run: py -3.11 scripts/release.py package-unified ${{ steps.version.outputs.version }} --output release/unified
```

- [ ] **Step 4: Add archive smoke tests**

Append Windows steps that expand each ZIP into distinct directories:

```yaml
      - name: Smoke-test Core archive
        shell: pwsh
        run: |
          Expand-Archive release/unified/empneon-core-v${{ steps.version.outputs.version }}.zip release/core-smoke
          py -3.11 -m venv release/core-smoke-venv
          $wheel = (Get-ChildItem release/core-smoke/wheels/empneon-*.whl).FullName
          & .\release\core-smoke-venv\Scripts\python.exe -m pip install $wheel
          & .\release\core-smoke-venv\Scripts\python.exe -c "import empneon; assert empneon.__version__ == '${{ steps.version.outputs.version }}'"
      - name: Smoke-test The Sims 4 archive
        shell: pwsh
        run: |
          Expand-Archive release/unified/empneon-thesims4-adapter-v${{ steps.version.outputs.version }}.zip release/sims-smoke
          & .\release\sims-smoke\run_backend.ps1 -InstallOnly
```

- [ ] **Step 5: Upload internal workflow artifacts**

Add:

```yaml
      - uses: actions/upload-artifact@v7
        with:
          name: unified-release-zips
          path: release/unified/*.zip
          if-no-files-found: error
          retention-days: 7
      - uses: actions/upload-artifact@v7
        with:
          name: core-python-distributions
          path: |
            core/dist/*.whl
            core/dist/*.tar.gz
          if-no-files-found: error
          retention-days: 7
```

- [ ] **Step 6: Add the release-attachment job**

Add:

```yaml
  attach-release-assets:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v8
        with:
          name: unified-release-zips
          path: release-assets
      - name: Attach archives to the triggering release
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
          GH_REPO: ${{ github.repository }}
          RELEASE_TAG: ${{ github.event.release.tag_name }}
        run: gh release upload "$RELEASE_TAG" release-assets/*.zip --clobber
```

- [ ] **Step 7: Add the isolated PyPI job**

Add:

```yaml
  publish-core:
    needs: [build, attach-release-assets]
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v8
        with:
          name: core-python-distributions
          path: dist
      - name: Publish Empneon Core to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/
```

- [ ] **Step 8: Run the workflow and release test suite**

Run:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider `
  scripts/test_release.py::test_unified_release_workflow_has_required_contract
py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py
```

Expected: all tests pass.

- [ ] **Step 9: Inspect YAML and formatting**

Run:

```powershell
git diff --check
git diff -- .github/workflows/unified-release.yml scripts/test_release.py
```

Expected: no whitespace errors; the workflow has no manual trigger, Godot archive, PyPI secret,
or release-creation command.

- [ ] **Step 10: Commit**

```powershell
git add -- .github/workflows/unified-release.yml scripts/test_release.py
git commit -m "ci: publish unified release artifacts"
```

---

### Task 3: Document and fully verify unified releases

**Files:**

- Modify: `README.md`
- Modify: `adapters/thesims4/README.md`
- Modify: `scripts/test_release.py`

**Interfaces:**

- Consumes: the approved archive names and `vX.Y.Z` release contract
- Produces: user-facing release instructions consistent with the generated assets

- [ ] **Step 1: Update the documentation contract test first**

Extend `test_release_documentation_matches_artifacts()` with:

```python
assert "empneon-core-vX.Y.Z.zip" in root_readme
assert "python -m pip install empneon" in root_readme
assert "empneon-thesims4-adapter-vX.Y.Z.zip" in sims_readme
assert "vX.Y.Z" in root_readme
```

Retain all assertions for independent `core-vX.Y.Z`, `thesims4-vX.Y.Z`, and `godot-vX.Y.Z`
releases.

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider `
  scripts/test_release.py::test_release_documentation_matches_artifacts
```

Expected: failure because the unified archive names and PyPI installation are not documented.

- [ ] **Step 3: Document unified Core releases**

In `README.md`, add to `## Releases`:

````markdown
Unified releases use the `vX.Y.Z` tag. Each release includes
`empneon-core-vX.Y.Z.zip`, containing the installable Core wheel. Core is also available from
PyPI:

```bash
python -m pip install empneon
```

Independent component tags such as `core-vX.Y.Z` remain supported.
````

Preserve the existing checksum and downloaded-wheel instructions.

- [ ] **Step 4: Document the unified Sims archive**

At the start of `adapters/thesims4/README.md` → `## Install a release`, add:

```markdown
From a unified `vX.Y.Z` release, download
`empneon-thesims4-adapter-vX.Y.Z.zip`. The existing independent
`thesims4-vX.Y.Z` release archive remains supported.
```

Keep the existing extraction, `install_mod.ps1`, and `run_backend.ps1` instructions.

- [ ] **Step 5: Run documentation and release tests**

Run:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider `
  scripts/test_release.py::test_release_documentation_matches_artifacts
py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py
```

Expected: all tests pass.

- [ ] **Step 6: Build real distributions and unified archives**

Run from repository root:

```powershell
py -3.12 -m build core
py -3.12 -m build adapters/thesims4
py -3.12 adapters/thesims4/build_mod.py
py -3.12 scripts/release.py package-unified 0.4.0 --output release/unified
py -3.12 -m twine check core/dist/* adapters/thesims4/dist/*.whl `
  adapters/thesims4/dist/*.tar.gz
```

Expected: both ZIPs are created; all Python distributions pass Twine validation.

- [ ] **Step 7: Inspect exact real archive members**

Run:

```powershell
@'
from pathlib import Path
from zipfile import ZipFile

for archive in sorted(Path("release/unified").glob("*.zip")):
    print(archive.name)
    with ZipFile(archive) as package:
        print("\n".join("  " + name for name in package.namelist()))
'@ | py -3.12 -
```

Expected: member lists exactly match the approved design; no Godot, test, database, capture, or
secret path appears.

- [ ] **Step 8: Run the complete automated test matrix**

Run:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

from `core`, then:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

from each adapter directory, then from repository root:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider tests scripts/test_release.py
```

Expected: Core, Sims, Godot, shared, and release tests all pass.

- [ ] **Step 9: Run final static and scope checks**

Run:

```powershell
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src `
  adapters/thesims4/tests adapters/godot/src adapters/godot/tests tests `
  scripts/release.py scripts/test_release.py
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m mypy core\src adapters\thesims4\src adapters\godot\src
git diff --check
git status --short
git diff --stat
```

Expected: lint, type checks, and whitespace checks pass; only unified-release implementation,
tests, and documentation are changed.

- [ ] **Step 10: Commit**

```powershell
git add -- README.md adapters/thesims4/README.md scripts/test_release.py
git commit -m "docs: document unified releases"
```

---

### Task 4: Configure the external Trusted Publisher

**Files:**

- No repository files

**Interfaces:**

- Consumes: `.github/workflows/unified-release.yml` and its `publish-core` job
- Produces: PyPI authorization for GitHub OIDC publication

- [ ] **Step 1: Create or verify the protected GitHub environment**

In repository settings, create environment `pypi`. Add required reviewers if release publication
must receive explicit approval. Do not add a PyPI API-token secret.

- [ ] **Step 2: Configure the PyPI Trusted Publisher**

In the `empneon` PyPI project Publishing settings, add:

```text
Owner: mf-rl
Repository: Empneon
Workflow: unified-release.yml
Environment: pypi
```

- [ ] **Step 3: Publish the first unified release**

Create and publish a GitHub release whose tag is exactly `v0.4.0`. Confirm the workflow:

- attaches `empneon-core-v0.4.0.zip`;
- attaches `empneon-thesims4-adapter-v0.4.0.zip`;
- attaches no Godot ZIP;
- publishes `empneon==0.4.0` to PyPI; and
- leaves the existing component releases untouched.

If `empneon==0.4.0` already exists on PyPI, use the next repository version; PyPI versions are
immutable and cannot be overwritten.
