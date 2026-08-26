#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Runs the full Empneon test suite with code coverage, then submits a SonarQube
    analysis (Community Edition, running locally in Docker) for the whole monorepo
    (Core + all adapters: The Sims 4, Godot).

.NOTES
    Requires:
      - A local SonarQube container reachable at http://localhost:9000
        (mapped to the host, e.g. the "sonarq-comm" container).
      - $env:SONAR_TOKEN set to a valid SonarQube user token. This script does NOT
        embed a token; it reads it from the environment so no secret is committed
        to source control.
      - .venv (Python 3.12) at the repo root with core/adapters installed in
        editable dev mode (see CONTRIBUTING.md).
      - Docker Desktop running, for the sonarsource/sonar-scanner-cli image.
#>

param(
    # Host as seen from inside the scanner container, not from the host machine.
    [string]$SonarHostUrl = "http://host.docker.internal:9000",
    # Host as seen from this script (the Sonar Web API is queried from here, not from the container).
    [string]$ApiHostUrl = "http://localhost:9000",
    [string]$ProjectKey = "Empneon",
    [string]$ReportPath = "sonar-report.json"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:SONAR_TOKEN) {
    throw "SONAR_TOKEN is not set. Run: `$env:SONAR_TOKEN = '<your token>' before calling this script."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw ".venv not found. Create it first: python -m venv .venv; then install `"core[dev]`" `"adapters/thesims4[dev]`" `"adapters/godot[dev]`""
}

Write-Host "==> Running Core tests with coverage" -ForegroundColor Cyan
& $venvPython -m pytest core --cov=core/src --cov-config=.coveragerc --cov-report=xml:core/coverage.xml

Write-Host "==> Running Godot adapter tests with coverage" -ForegroundColor Cyan
& $venvPython -m pytest adapters/godot --cov=adapters/godot/src --cov-config=.coveragerc --cov-report=xml:adapters/godot/coverage.xml

Write-Host "==> Running The Sims 4 adapter tests with coverage" -ForegroundColor Cyan
& $venvPython -m pytest adapters/thesims4 --cov=adapters/thesims4/src --cov=adapters/thesims4/backend --cov=adapters/thesims4/scripts --cov=adapters/thesims4/ts4script --cov-config=.coveragerc --cov-report=xml:adapters/thesims4/coverage.xml

Write-Host "==> Running cross-adapter tests with coverage" -ForegroundColor Cyan
& $venvPython -m pytest tests --cov=core/src --cov=adapters/godot/src --cov=adapters/thesims4/src --cov-config=.coveragerc --cov-report=xml:coverage-cross.xml

Write-Host "==> Running release script tests with coverage" -ForegroundColor Cyan
& $venvPython -m pytest scripts --cov=scripts --cov-config=.coveragerc --cov-report=xml:coverage-scripts.xml

Write-Host "==> Running SonarQube scan (sonarsource/sonar-scanner-cli, Community Edition)" -ForegroundColor Cyan
$scanLines = @()
docker run --rm `
    --add-host=host.docker.internal:host-gateway `
    -e SONAR_HOST_URL="$SonarHostUrl" `
    -e SONAR_TOKEN="$env:SONAR_TOKEN" `
    -v "${PWD}:/usr/src" `
    sonarsource/sonar-scanner-cli 2>&1 | ForEach-Object {
        Write-Host $_
        $scanLines += "$_"
    }

if ($LASTEXITCODE -ne 0) {
    throw "sonar-scanner failed with exit code $LASTEXITCODE"
}

$ceTaskLine = $scanLines | Where-Object { $_ -match 'api/ce/task\?id=([a-zA-Z0-9\-]+)' } | Select-Object -First 1
if (-not $ceTaskLine -or -not ($ceTaskLine -match 'api/ce/task\?id=([a-zA-Z0-9\-]+)')) {
    throw "Could not find the background task id in the scanner output; cannot fetch the report."
}
$ceTaskId = $Matches[1]

$authHeader = @{
    Authorization = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($env:SONAR_TOKEN):"))
}

Write-Host "==> Waiting for SonarQube to process the analysis report (task $ceTaskId)" -ForegroundColor Cyan
$taskStatus = "PENDING"
$attempt = 0
while ($taskStatus -in @("PENDING", "IN_PROGRESS") -and $attempt -lt 60) {
    Start-Sleep -Seconds 2
    $taskResponse = Invoke-RestMethod -Uri "$ApiHostUrl/api/ce/task?id=$ceTaskId" -Headers $authHeader
    $taskStatus = $taskResponse.task.status
    $attempt++
}
if ($taskStatus -ne "SUCCESS") {
    throw "SonarQube background task did not succeed (status: $taskStatus)"
}

Write-Host "==> Fetching issues, hotspots and measures from the Sonar Web API" -ForegroundColor Cyan

function Get-AllPages {
    param([string]$UrlWithoutPage, [string]$ListProperty)
    $items = @()
    $page = 1
    do {
        $response = Invoke-RestMethod -Uri "$UrlWithoutPage&p=$page" -Headers $authHeader
        $items += $response.$ListProperty
        $page++
    } while (($page - 1) * 500 -lt $response.paging.total)
    return $items
}

# Project Analysis Tokens (sqp_...) can push a scan but lack Browse permission for these
# read endpoints. Fall back to an empty result instead of failing the whole report.
$apiErrors = @()
$issues = @()
$hotspots = @()
$summary = @{}

try {
    $issues = Get-AllPages -UrlWithoutPage "$ApiHostUrl/api/issues/search?componentKeys=$ProjectKey&resolved=false&ps=500" -ListProperty "issues"
} catch {
    $apiErrors += "issues/search failed: $($_.Exception.Message). Use a User Token (not a Project Analysis Token) for SONAR_TOKEN to enable this."
}

try {
    $hotspots = Get-AllPages -UrlWithoutPage "$ApiHostUrl/api/hotspots/search?projectKey=$ProjectKey&ps=500" -ListProperty "hotspots"
} catch {
    $apiErrors += "hotspots/search failed: $($_.Exception.Message). Use a User Token (not a Project Analysis Token) for SONAR_TOKEN to enable this."
}

try {
    $metricKeys = "bugs,vulnerabilities,code_smells,security_hotspots,coverage,line_coverage,branch_coverage,uncovered_lines,lines_to_cover,duplicated_lines_density,ncloc,reliability_rating,security_rating,sqale_rating"
    $measuresResponse = Invoke-RestMethod -Uri "$ApiHostUrl/api/measures/component?component=$ProjectKey&metricKeys=$metricKeys" -Headers $authHeader
    foreach ($measure in $measuresResponse.component.measures) { $summary[$measure.metric] = $measure.value }
} catch {
    $apiErrors += "measures/component failed: $($_.Exception.Message). Use a User Token (not a Project Analysis Token) for SONAR_TOKEN to enable this."
}

$curatedIssues = $issues | ForEach-Object {
    [PSCustomObject]@{
        key          = $_.key
        rule         = $_.rule
        severity     = $_.severity
        type         = $_.type
        component    = $_.component -replace "^$([regex]::Escape($ProjectKey)):", ""
        line         = $_.line
        textRange    = $_.textRange
        message      = $_.message
        effort       = $_.effort
        tags         = $_.tags
        status       = $_.status
        creationDate = $_.creationDate
    }
}

$curatedHotspots = $hotspots | ForEach-Object {
    [PSCustomObject]@{
        key          = $_.key
        rule         = $_.ruleKey
        vulnerabilityProbability = $_.vulnerabilityProbability
        status       = $_.status
        component    = $_.component -replace "^$([regex]::Escape($ProjectKey)):", ""
        line         = $_.line
        message      = $_.message
        creationDate = $_.creationDate
    }
}

$report = [PSCustomObject]@{
    generatedAt   = (Get-Date).ToString("o")
    projectKey    = $ProjectKey
    sonarHostUrl  = $ApiHostUrl
    dashboardUrl  = "$ApiHostUrl/dashboard?id=$ProjectKey"
    ceTaskId      = $ceTaskId
    apiErrors     = $apiErrors
    summary       = $summary
    issuesTotal   = $curatedIssues.Count
    issues        = $curatedIssues
    hotspotsTotal = $curatedHotspots.Count
    hotspots      = $curatedHotspots
}

$reportFullPath = Join-Path $PSScriptRoot $ReportPath
$report | ConvertTo-Json -Depth 10 | Set-Content -Path $reportFullPath -Encoding utf8

if ($apiErrors.Count -gt 0) {
    Write-Host "==> Report written with gaps - see apiErrors in the JSON:" -ForegroundColor Yellow
    $apiErrors | ForEach-Object { Write-Host "    - $_" -ForegroundColor Yellow }
}
Write-Host "==> Scan complete. $($curatedIssues.Count) issues, $($curatedHotspots.Count) hotspots, coverage=$($summary['coverage'])%" -ForegroundColor Green
Write-Host "==> Report written to $reportFullPath" -ForegroundColor Green
Write-Host "==> Dashboard: $ApiHostUrl/dashboard?id=$ProjectKey" -ForegroundColor Green
