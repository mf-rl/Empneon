$ErrorActionPreference = "Stop"

$scriptSource = Join-Path $PSScriptRoot "dist\Empneon_TheSims4.ts4script"
$tuningSource = Join-Path $PSScriptRoot "dist\Empneon_TheSims4.package"
$builder = Join-Path $PSScriptRoot "build_mod.py"
if (Test-Path $builder) {
    python $builder
} elseif (-not ((Test-Path $scriptSource) -and (Test-Path $tuningSource))) {
    throw "Prebuilt Empneon mod files are missing. Download the complete release ZIP."
}

$game = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Electronic Arts\The Sims 4"
$mods = Join-Path $game "Mods"
$target = Join-Path $mods "Empneon_TheSims4.ts4script"
$tuningTarget = Join-Path $mods "Empneon_TheSims4.package"
@(
    (Join-Path $mods "AI Sims Agent\AI_Sims_Agent.ts4script"),
    (Join-Path $mods "AI_Sims_Agent.ts4script"),
    (Join-Path $mods "AI_Sims_Agent.package"),
    $target,
    $tuningTarget
) | ForEach-Object { Remove-Item -Force $_ -ErrorAction SilentlyContinue }
Remove-Item -Force (Join-Path $game "localthumbcache.package") -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $game "ai_sims_agent_loaded.txt") -ErrorAction SilentlyContinue
Copy-Item -Force $scriptSource $target
Copy-Item -Force $tuningSource $tuningTarget
$now = Get-Date
(Get-Item $target).CreationTime = $now
(Get-Item $target).LastWriteTime = $now
(Get-Item $tuningTarget).CreationTime = $now
(Get-Item $tuningTarget).LastWriteTime = $now

Write-Host "Installed to $mods"
