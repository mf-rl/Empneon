$ErrorActionPreference = "Stop"

$coreSrc = Join-Path $PSScriptRoot "..\..\core\src"
if (Test-Path $coreSrc) {
    $env:PYTHONPATH = if ($env:PYTHONPATH) {
        "$coreSrc$([IO.Path]::PathSeparator)$env:PYTHONPATH"
    } else {
        $coreSrc
    }
}

py -3 "$PSScriptRoot\backend\ai_sims_server.py"
