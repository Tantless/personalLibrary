param(
    [string]$ManifestPath = ".trellis/tasks/06-18-pkcs-m3-baseline-corpus-v1/selected-sources-v1-draft.jsonl",
    [string]$TaskDir = ".trellis/tasks/06-18-pkcs-m3-baseline-corpus-v1"
)

$ErrorActionPreference = "Stop"
$RunDirs = @(Get-ChildItem $TaskDir -Directory -Filter "full-reingest-*" | Sort-Object Name)
if ($RunDirs.Count -eq 0) {
    throw "no full-reingest report directories found"
}

$SummaryDir = Join-Path $TaskDir "final-reingest-validation"
$RowsPath = Join-Path $SummaryDir "validation.jsonl"
$SummaryPath = Join-Path $SummaryDir "summary.json"
$ReportPath = Join-Path $SummaryDir "reingestion-result.md"

function Resolve-OutputPath {
    param([string]$Path)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $executionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Resolve-OutputPath $Path), $Text, $encoding)
}

function Add-JsonlRow {
    param([string]$Path, [object]$Row)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::AppendAllText((Resolve-OutputPath $Path), (($Row | ConvertTo-Json -Depth 30 -Compress) + "`n"), $encoding)
}

function Get-EffectiveSource {
    param($Row)
    $replacement = $Row.v1_replacement
    if ($replacement -and $replacement.v1_url) {
        return [pscustomobject]@{
            Url = [string]$replacement.v1_url
            Format = [string]$replacement.v1_format
            Strategy = [string]$replacement.v1_conversion_strategy
            Title = [string]$replacement.v1_title
        }
    }
    return [pscustomobject]@{
        Url = [string]$Row.url
        Format = [string]$Row.format
        Strategy = [string]$Row.conversion_strategy
        Title = [string]$Row.expected_title
    }
}

function Import-ReportMap {
    param([string]$FileName)
    $map = @{}
    foreach ($dir in $RunDirs) {
        $path = Join-Path $dir.FullName $FileName
        if (-not (Test-Path $path)) { continue }
        foreach ($line in Get-Content $path -Encoding UTF8) {
            if (-not $line.Trim()) { continue }
            $row = $line | ConvertFrom-Json
            $map[[string]$row.id] = $row
        }
    }
    return $map
}

function Get-DbSourceStats {
    $sql = @"
select
  s.canonical_key,
  s.title,
  count(distinct c.id) as chunks,
  count(distinct ia.id) as images,
  count(distinct ta.id) as tables
from sources s
left join chunks c on c.source_id = s.id
left join image_artifacts ia on ia.source_id = s.id
left join table_artifacts ta on ta.source_id = s.id
group by s.canonical_key, s.title
order by s.canonical_key;
"@
    $output = docker exec pkcs-postgres psql -U pkcs -d pkcs -t -A -F "`t" -c $sql
    $stats = @{}
    foreach ($line in $output) {
        if (-not $line.Trim()) { continue }
        $parts = $line.Split("`t")
        if ($parts.Count -ge 5) {
            $stats[$parts[0]] = [pscustomobject]@{
                canonical_key = $parts[0]
                title = $parts[1]
                chunks = [int]$parts[2]
                images = [int]$parts[3]
                tables = [int]$parts[4]
            }
        }
    }
    return $stats
}

function Get-DbCounts {
    $sql = "select 'sources' table_name, count(*) from sources union all select 'source_versions', count(*) from source_versions union all select 'chunks', count(*) from chunks union all select 'table_artifacts', count(*) from table_artifacts union all select 'image_artifacts', count(*) from image_artifacts union all select 'ingest_jobs', count(*) from ingest_jobs;"
    $output = docker exec pkcs-postgres psql -U pkcs -d pkcs -t -A -F "|" -c $sql
    $counts = @{}
    foreach ($line in $output) {
        if (-not $line.Trim()) { continue }
        $parts = $line.Split("|")
        if ($parts.Count -eq 2) {
            $counts[$parts[0]] = [int]$parts[1]
        }
    }
    return $counts
}

function Invoke-SearchSmoke {
    param($Row)
    $queries = @($Row.validation_queries)
    $query = [string]($queries | Select-Object -First 1)
    if (-not $query) {
        $query = [string]$Row.expected_title
    }
    $output = & ".venv/Scripts/pkcs.exe" search $query --canonical-key $Row.canonical_key --top-k 3 2>&1
    $exitCode = $LASTEXITCODE
    $parsed = $null
    try {
        $parsed = ($output | Select-Object -Last 1) | ConvertFrom-Json
    } catch {
        $parsed = $null
    }
    $count = 0
    if ($parsed -and $parsed.results) {
        $count = @($parsed.results).Count
    }
    return [pscustomobject]@{
        query = $query
        exit_code = $exitCode
        result_count = $count
        passed = ($exitCode -eq 0 -and $count -gt 0)
    }
}

function Test-HasReportHits {
    param($Value)
    if ($null -eq $Value) {
        return $false
    }
    if ($Value -is [string]) {
        return -not [string]::IsNullOrWhiteSpace($Value)
    }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        return @($Value.PSObject.Properties).Count -gt 0
    }
    return @($Value).Count -gt 0
}

$manifestRows = @(Get-Content $ManifestPath -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
$sourceMap = Import-ReportMap -FileName "source-validation.jsonl"
$prepareMap = Import-ReportMap -FileName "prepare.jsonl"
$ingestMap = Import-ReportMap -FileName "ingest.jsonl"
$dbStats = Get-DbSourceStats
$dbCounts = Get-DbCounts

if (Test-Path $RowsPath) {
    Remove-Item -LiteralPath $RowsPath -Force
}

$validationRows = @()
foreach ($row in $manifestRows) {
    $source = Get-EffectiveSource $row
    $sourceReport = $sourceMap[[string]$row.id]
    $prepareReport = $prepareMap[[string]$row.id]
    $ingestReport = $ingestMap[[string]$row.id]
    $db = $dbStats[[string]$row.canonical_key]
    $search = Invoke-SearchSmoke -Row $row

    $failures = @()
    if (-not $sourceReport -or $sourceReport.validation_status -notmatch "^downloaded") { $failures += "source_not_downloaded" }
    if (-not $prepareReport -or $prepareReport.prepare_status -eq "hard_fail") { $failures += "prepare_failed" }
    if (-not $ingestReport -or $ingestReport.ingest_status -notin @("completed", "succeeded")) { $failures += "ingest_failed" }
    if (-not $db) { $failures += "missing_db_source" }
    if ($db -and $db.title -ne $source.Title) { $failures += "title_mismatch" }
    if ($db -and $db.chunks -lt [int]$row.minimum_quality_gate.min_chunks) { $failures += "too_few_chunks" }
    if (-not $search.passed) { $failures += "search_smoke_failed" }
    if ($sourceReport -and (Test-HasReportHits $sourceReport.reject_hits)) { $failures += "source_reject_pattern_found" }
    if ($prepareReport -and (Test-HasReportHits $prepareReport.reject_hits)) { $failures += "document_reject_pattern_found" }
    if ($prepareReport -and $prepareReport.document_chars -lt [int]$row.minimum_quality_gate.min_document_chars) { $failures += "document_too_short" }

    $localArtifactCount = 0
    if ($prepareReport -and $prepareReport.counts) {
        $localArtifactCount = [int]$prepareReport.counts.local_images + [int]$prepareReport.counts.inline_tables + [int]$prepareReport.counts.sidecar_tables
    }
    if ($row.minimum_quality_gate.require_local_artifact -eq $true -and $localArtifactCount -le 0) {
        $failures += "local_artifact_required_but_missing"
    }

    $validationRow = [pscustomobject]@{
        id = $row.id
        canonical_key = $row.canonical_key
        expected_title = $source.Title
        db_title = if ($db) { $db.title } else { $null }
        quality_tier = $row.quality_tier
        decision = $row.decision
        conversion_strategy = $source.Strategy
        fallback_used = if ($prepareReport) { $prepareReport.fallback_used } else { $null }
        prepare_status = if ($prepareReport) { $prepareReport.prepare_status } else { $null }
        ingest_status = if ($ingestReport) { $ingestReport.ingest_status } else { $null }
        document_chars = if ($prepareReport) { [int]$prepareReport.document_chars } else { 0 }
        chunks = if ($db) { $db.chunks } else { 0 }
        db_images = if ($db) { $db.images } else { 0 }
        db_tables = if ($db) { $db.tables } else { 0 }
        local_artifact_count = $localArtifactCount
        search_smoke = $search
        validation_status = if ($failures.Count -eq 0) { "pass" } else { "fail" }
        failures = $failures
    }
    Add-JsonlRow -Path $RowsPath -Row $validationRow
    $validationRows += $validationRow
}

$fallbackCounts = @{}
foreach ($item in $validationRows) {
    $key = if ($item.fallback_used) { [string]$item.fallback_used } else { "none" }
    if (-not $fallbackCounts.ContainsKey($key)) { $fallbackCounts[$key] = 0 }
    $fallbackCounts[$key] += 1
}

$summary = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    manifest_count = $manifestRows.Count
    db_counts = $dbCounts
    validation = [pscustomobject]@{
        pass = @($validationRows | Where-Object { $_.validation_status -eq "pass" }).Count
        fail = @($validationRows | Where-Object { $_.validation_status -eq "fail" }).Count
        search_smoke_pass = @($validationRows | Where-Object { $_.search_smoke.passed }).Count
        title_mismatches = @($validationRows | Where-Object { $_.failures -contains "title_mismatch" }).Count
        reject_pattern_rows = @($validationRows | Where-Object { ($_.failures -contains "source_reject_pattern_found") -or ($_.failures -contains "document_reject_pattern_found") }).Count
        missing_db_sources = @($validationRows | Where-Object { $_.failures -contains "missing_db_source" }).Count
        local_artifact_ready_rows = @($validationRows | Where-Object { $_.local_artifact_count -gt 0 }).Count
    }
    by_quality_tier = @(
        $validationRows | Group-Object quality_tier | ForEach-Object {
            [pscustomobject]@{
                quality_tier = $_.Name
                count = $_.Count
                pass = @($_.Group | Where-Object { $_.validation_status -eq "pass" }).Count
                local_artifact_ready = @($_.Group | Where-Object { $_.local_artifact_count -gt 0 }).Count
            }
        }
    )
    fallback_counts = $fallbackCounts
    failed_rows = @($validationRows | Where-Object { $_.validation_status -eq "fail" } | Select-Object id, canonical_key, failures)
    source_report_dirs = @($RunDirs | ForEach-Object { $_.FullName })
}

Write-Utf8NoBom -Path $SummaryPath -Text (($summary | ConvertTo-Json -Depth 30) + "`n")

$mdLines = @(
    "# M3 baseline corpus v1 reingestion result",
    "",
    "## Result",
    "",
    "* manifest rows: $($summary.manifest_count)",
    "* DB sources: $($dbCounts["sources"])",
    "* DB source versions: $($dbCounts["source_versions"])",
    "* DB chunks: $($dbCounts["chunks"])",
    "* DB image artifacts: $($dbCounts["image_artifacts"])",
    "* DB table artifacts: $($dbCounts["table_artifacts"])",
    "* validation pass: $($summary.validation.pass)",
    "* validation fail: $($summary.validation.fail)",
    "* search smoke pass: $($summary.validation.search_smoke_pass)",
    "* title mismatches: $($summary.validation.title_mismatches)",
    "* reject-pattern rows: $($summary.validation.reject_pattern_rows)",
    "* local artifact-ready rows: $($summary.validation.local_artifact_ready_rows)",
    "",
    "## Notes",
    "",
    "* The full run reset PKCS business tables and cleared ``data/raw`` / ``data/private`` before ingesting v1.",
    "* Ingestion used ``.venv/Scripts/pkcs.exe`` CLI, which calls the same PKCS application service as the MCP ingest path.",
    "* ``M3-ANIME-021`` required the explicit ``markdown_utf8_sanitized`` fallback and was patched in a second no-reset run.",
    "* Reader Markdown snapshots were used where public HTML was more stable through reader conversion than direct Docling HTML conversion.",
    "",
    "## Reports",
    "",
    "* Per-row validation: ``validation.jsonl``",
    "* Machine summary: ``summary.json``"
)

Write-Utf8NoBom -Path $ReportPath -Text (($mdLines -join "`n") + "`n")
$summary | ConvertTo-Json -Depth 30
