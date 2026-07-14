$ErrorActionPreference = "Stop"

python "$PSScriptRoot\build_mod.py"

$game = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Electronic Arts\The Sims 4"
$mods = Join-Path $game "Mods"
$old = Join-Path $mods "AI Sims Agent\AI_Sims_Agent.ts4script"
$target = Join-Path $mods "AI_Sims_Agent.ts4script"
$tuningTarget = Join-Path $mods "AI_Sims_Agent.package"
Remove-Item -Force $old -ErrorAction SilentlyContinue
Remove-Item -Force $target -ErrorAction SilentlyContinue
Remove-Item -Force $tuningTarget -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $game "localthumbcache.package") -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $game "ai_sims_agent_loaded.txt") -ErrorAction SilentlyContinue
Copy-Item -Force "$PSScriptRoot\dist\AI_Sims_Agent.ts4script" $target
Copy-Item -Force "$PSScriptRoot\dist\AI_Sims_Agent.package" $tuningTarget
$now = Get-Date
(Get-Item $target).CreationTime = $now
(Get-Item $target).LastWriteTime = $now
(Get-Item $tuningTarget).CreationTime = $now
(Get-Item $tuningTarget).LastWriteTime = $now

Write-Host "Installed to $mods"
