param([switch]$InstallOnly)

$ErrorActionPreference = "Stop"

$python = "py"
$pythonArgs = @("-3")
$wheelDir = Join-Path $PSScriptRoot "wheels"

if (Test-Path $wheelDir) {
    & py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
    if ($LASTEXITCODE -ne 0) {
        throw "Empneon requires Python 3.11 or newer."
    }

    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        & py -3 -m venv (Join-Path $PSScriptRoot ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the Empneon virtual environment."
        }
    }

    $coreWheel = @(Get-ChildItem $wheelDir -Filter "empneon-*.whl" -File)
    $adapterWheel = @(Get-ChildItem $wheelDir -Filter "empneon_thesims4-*.whl" -File)
    if ($coreWheel.Count -ne 1 -or $adapterWheel.Count -ne 1) {
        throw "The release must contain one Empneon Core wheel and one The Sims 4 wheel."
    }

    & $python -m pip install --disable-pip-version-check --upgrade `
        $coreWheel[0].FullName $adapterWheel[0].FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the bundled Empneon packages. Check your internet connection."
    }
    $pythonArgs = @()
}

if ($InstallOnly) {
    & $python @pythonArgs -c "import empneon, empneon_thesims4"
    exit $LASTEXITCODE
}

& $python @pythonArgs "$PSScriptRoot\backend\ai_sims_server.py"
exit $LASTEXITCODE
