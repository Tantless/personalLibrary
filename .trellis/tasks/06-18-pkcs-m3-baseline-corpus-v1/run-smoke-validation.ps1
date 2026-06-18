param(
    [string]$ManifestPath = ".trellis/tasks/06-18-pkcs-m3-baseline-corpus-v1/selected-sources-v1-draft.jsonl",
    [string]$TaskDir = ".trellis/tasks/06-18-pkcs-m3-baseline-corpus-v1",
    [string[]]$OnlyIds = @(),
    [switch]$SkipPrepare
)

$ErrorActionPreference = "Stop"

$SmokeIds = @(
    "M3-AI-002",
    "M3-AI-001",
    "M3-AI-041",
    "M3-AI-019",
    "M3-ANIME-005",
    "M3-ANIME-013",
    "M3-GAME-030",
    "M3-GAME-002",
    "M3-GAME-003",
    "M3-GAME-006",
    "M3-GAME-015",
    "M3-GAME-016"
)

$SmokeReasons = @{
    "M3-AI-002" = "direct markdown artifact-ready source"
    "M3-AI-001" = "PDF text-only pdftotext fallback"
    "M3-AI-041" = "DOCX artifact-ready source"
    "M3-AI-019" = "recent AI news HTML repair case"
    "M3-ANIME-005" = "anime PDF artifact-ready source"
    "M3-ANIME-013" = "anime interview HTML/reader repair case"
    "M3-GAME-030" = "game direct markdown source"
    "M3-GAME-002" = "Epic doc replacement for challenge snapshot"
    "M3-GAME-003" = "Epic news/release replacement for challenge snapshot"
    "M3-GAME-006" = "Unreal EULA replacement using stable PDF"
    "M3-GAME-015" = "Unity concrete manual replacement"
    "M3-GAME-016" = "Unity richer manual replacement"
}

if ($OnlyIds.Count -gt 0) {
    $SmokeIds = $SmokeIds | Where-Object { $OnlyIds -contains $_ }
}

$RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$PrivateRoot = Join-Path (Get-Location) "data/private/m3-baseline-v1/smoke"
$DownloadRoot = Join-Path $PrivateRoot "source-downloads"
$SnapshotRoot = Join-Path $PrivateRoot "snapshots"
$PrepRoot = Join-Path $PrivateRoot "ingest-prep"
New-Item -ItemType Directory -Force -Path $DownloadRoot, $SnapshotRoot, $PrepRoot | Out-Null

$SelectionPath = Join-Path $TaskDir "smoke-batch-selection.jsonl"
$SourceReportPath = Join-Path $TaskDir "smoke-source-validation-report.jsonl"
$PrepareReportPath = Join-Path $TaskDir "smoke-prepare-report.jsonl"
$SummaryPath = Join-Path $TaskDir "smoke-quality-gate-report.json"

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Resolve-OutputPath $Path), $Text, $encoding)
}

function Resolve-OutputPath {
    param([string]$Path)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $executionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
}

function Write-Jsonl {
    param([string]$Path, [array]$Rows)
    $lines = @()
    foreach ($row in $Rows) {
        $lines += ($row | ConvertTo-Json -Depth 20 -Compress)
    }
    Write-Utf8NoBom -Path $Path -Text (($lines -join "`n") + "`n")
}

function Get-DownloadExtension {
    param([string]$Format, [string]$Url, [string]$Strategy)
    $strategyLower = ""
    if ($Strategy) {
        $strategyLower = $Strategy.ToLowerInvariant()
    }
    if ($strategyLower -match "pdf_") { return ".pdf" }
    if ($strategyLower -match "docx") { return ".docx" }
    if ($strategyLower -match "html|reader|static") { return ".html" }

    $uriPath = ([System.Uri]$Url).AbsolutePath.ToLowerInvariant()
    foreach ($ext in @(".pdf", ".docx", ".html", ".htm", ".md")) {
        if ($uriPath.EndsWith($ext)) { return $ext }
    }

    $lower = ""
    if ($Format) {
        $lower = $Format.ToLowerInvariant()
    }
    if ($lower -in @("md", "markdown")) { return ".md" }
    if ($lower -eq "pdf") { return ".pdf" }
    if ($lower -eq "docx") { return ".docx" }
    if ($lower -eq "html" -or $lower -eq "htm") { return ".html" }
    return ".source"
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
            Replacement = $true
        }
    }
    return [pscustomobject]@{
        Url = [string]$Row.url
        Format = [string]$Row.format
        Strategy = [string]$Row.conversion_strategy
        Title = [string]$Row.expected_title
        Replacement = $false
    }
}

function Invoke-CurlDownload {
    param(
        [string]$Url,
        [string]$Destination,
        [int]$MaxTimeSeconds = 120
    )
    $Destination = Resolve-OutputPath $Destination
    $metadataFormat = "PKCSMETA:%{http_code}|%{content_type}|%{size_download}|%{url_effective}"
    $args = @(
        "-L",
        "--silent",
        "--show-error",
        "--connect-timeout", "20",
        "--max-time", [string]$MaxTimeSeconds,
        "-A", "Mozilla/5.0 PKCS-M3-Baseline-Smoke",
        "-o", $Destination,
        "-w", "`n$metadataFormat",
        $Url
    )
    $output = & curl.exe @args 2>&1
    $exitCode = $LASTEXITCODE
    $metaLine = ($output | Where-Object { $_ -like "PKCSMETA:*" } | Select-Object -Last 1)
    $httpCode = $null
    $contentType = $null
    $sizeDownload = $null
    $effectiveUrl = $null
    if ($metaLine) {
        $parts = $metaLine.Substring("PKCSMETA:".Length).Split("|", 4)
        if ($parts.Count -ge 4) {
            $httpCode = $parts[0]
            $contentType = $parts[1]
            $sizeDownload = [double]$parts[2]
            $effectiveUrl = $parts[3]
        }
    }
    return [pscustomobject]@{
        exit_code = $exitCode
        http_code = $httpCode
        content_type = $contentType
        size_download = $sizeDownload
        effective_url = $effectiveUrl
        output_tail = (($output | Where-Object { $_ -notlike "PKCSMETA:*" } | Select-Object -Last 5) -join "`n")
        destination = $Destination
    }
}

function Get-TextIfReadable {
    param([string]$Path)
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($ext -notin @(".md", ".markdown", ".txt", ".html", ".htm", ".json")) {
        return ""
    }
    try {
        return [System.IO.File]::ReadAllText((Resolve-OutputPath $Path), [System.Text.Encoding]::UTF8)
    } catch {
        return ""
    }
}

function Find-RejectHits {
    param([string]$Text, [array]$Patterns)
    $hits = @()
    foreach ($pattern in $Patterns) {
        if ($Text -and $Text.IndexOf([string]$pattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $hits += [string]$pattern
        }
    }
    return $hits
}

function New-ReaderUrl {
    param([string]$Url)
    return "https://r.jina.ai/http://$Url"
}

function New-PdfTextMarkdown {
    param(
        [string]$PdfPath,
        [string]$MarkdownPath,
        [string]$Title,
        [string]$Url
    )
    $pdftotext = Get-Command pdftotext -ErrorAction Stop
    $txtPath = [System.IO.Path]::ChangeExtension((Resolve-OutputPath $MarkdownPath), ".txt")
    & $pdftotext.Source -layout (Resolve-OutputPath $PdfPath) $txtPath
    if ($LASTEXITCODE -ne 0) {
        throw "pdftotext failed for $PdfPath"
    }
    $plain = [System.IO.File]::ReadAllText($txtPath, [System.Text.Encoding]::UTF8)
    $markdown = "# $Title`n`nSource URL: $Url`n`n$plain"
    Write-Utf8NoBom -Path $MarkdownPath -Text $markdown
    return Resolve-OutputPath $MarkdownPath
}

function Invoke-PrepareIngest {
    param(
        [string]$InputPath,
        [string]$Id,
        [int]$TimeoutSeconds
    )
    $slug = "v1-smoke-$($Id.ToLowerInvariant())-$RunStamp"
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $output = & ".venv/Scripts/pkcs.exe" prepare-ingest $InputPath --output-root $PrepRoot --slug $slug --timeout-seconds $TimeoutSeconds 2>&1
    $timer.Stop()
    $exitCode = $LASTEXITCODE
    $jsonText = ($output | Select-Object -Last 1)
    $parsed = $null
    try {
        $parsed = $jsonText | ConvertFrom-Json
    } catch {
        $parsed = $null
    }
    return [pscustomobject]@{
        exit_code = $exitCode
        elapsed_seconds = [math]::Round($timer.Elapsed.TotalSeconds, 2)
        raw_output_tail = (($output | Select-Object -Last 10) -join "`n")
        parsed = $parsed
    }
}

$RowsById = @{}
foreach ($line in Get-Content $ManifestPath -Encoding UTF8) {
    if (-not $line.Trim()) { continue }
    $row = $line | ConvertFrom-Json
    $RowsById[$row.id] = $row
}

$selectionRows = @()
$sourceRows = @()
$prepareRows = @()

foreach ($id in $SmokeIds) {
    if (-not $RowsById.ContainsKey($id)) {
        throw "smoke id not found in manifest: $id"
    }
    $row = $RowsById[$id]
    $source = Get-EffectiveSource $row
    $gate = $row.minimum_quality_gate
    $minChars = [int]$gate.min_document_chars
    $rejectPatterns = @($gate.reject_patterns)
    $ext = Get-DownloadExtension -Format $source.Format -Url $source.Url -Strategy $source.Strategy
    $safeName = $id.ToLowerInvariant()
    $downloadPath = Join-Path $DownloadRoot "$safeName$ext"

    $selectionRows += [pscustomobject]@{
        id = $id
        reason = $SmokeReasons[$id]
        effective_url = $source.Url
        effective_format = $source.Format
        conversion_strategy = $source.Strategy
        expected_title = $source.Title
        is_replacement = $source.Replacement
    }

    Write-Host "[$id] download $($source.Url)"
    $download = Invoke-CurlDownload -Url $source.Url -Destination $downloadPath -MaxTimeSeconds 180
    $text = Get-TextIfReadable $download.destination
    $rejectHits = Find-RejectHits -Text $text -Patterns $rejectPatterns
    $fallbackUsed = $null
    $prepareInput = $download.destination
    $validationStatus = "downloaded"
    $isHtmlDownload = (($download.content_type -and $download.content_type.ToLowerInvariant().Contains("html")) -or $text.TrimStart().StartsWith("<!DOCTYPE html", [System.StringComparison]::OrdinalIgnoreCase) -or $text.TrimStart().StartsWith("<html", [System.StringComparison]::OrdinalIgnoreCase))

    if ($isHtmlDownload -and ([System.IO.Path]::GetExtension($download.destination).ToLowerInvariant() -notin @(".html", ".htm"))) {
        $htmlPath = Join-Path $DownloadRoot "$safeName.html"
        Move-Item -Force -Path $download.destination -Destination $htmlPath
        $download.destination = Resolve-OutputPath $htmlPath
        $prepareInput = $download.destination
    }

    if ($download.exit_code -ne 0 -or -not ($download.http_code -match "^2")) {
        $validationStatus = "download_failed"
    }

    if ($isHtmlDownload -and $source.Strategy -notmatch "static_html" -and ($source.Strategy -match "reader" -or $rejectHits.Count -gt 0 -or $text.Length -lt [math]::Min($minChars, 3000) -or $source.Url -notmatch "raw\.githubusercontent\.com")) {
        $readerPath = Join-Path $SnapshotRoot "$safeName.reader.md"
        $readerDownload = Invoke-CurlDownload -Url (New-ReaderUrl $source.Url) -Destination $readerPath -MaxTimeSeconds 180
        $readerText = Get-TextIfReadable $readerDownload.destination
        $readerRejectHits = Find-RejectHits -Text $readerText -Patterns $rejectPatterns
        if ($readerDownload.exit_code -eq 0 -and $readerDownload.http_code -match "^2" -and $readerRejectHits.Count -eq 0 -and $readerText.Length -ge [math]::Min($minChars, 3000)) {
            $prepareInput = $readerDownload.destination
            $fallbackUsed = "reader_markdown"
            $text = $readerText
            $rejectHits = $readerRejectHits
            $validationStatus = "downloaded_with_reader_snapshot"
        } else {
            $fallbackUsed = "reader_rejected"
        }
    }

    if ($source.Strategy -eq "pdf_text_only_pdftotext") {
        $snapshotPath = Join-Path $SnapshotRoot "$safeName.pdftotext.md"
        $prepareInput = New-PdfTextMarkdown -PdfPath $download.destination -MarkdownPath $snapshotPath -Title $source.Title -Url $source.Url
        $text = Get-TextIfReadable $prepareInput
        $rejectHits = Find-RejectHits -Text $text -Patterns $rejectPatterns
        $fallbackUsed = "pdftotext_markdown"
    }

    $sourceRows += [pscustomobject]@{
        id = $id
        url = $source.Url
        format = $source.Format
        strategy = $source.Strategy
        validation_status = $validationStatus
        http_code = $download.http_code
        content_type = $download.content_type
        size_download = $download.size_download
        source_path = $download.destination
        prepare_input_path = $prepareInput
        fallback_used = $fallbackUsed
        readable_chars = $text.Length
        reject_hits = $rejectHits
    }

    if ($SkipPrepare) {
        continue
    }

    $timeout = 30
    if ($source.Strategy -match "docx") { $timeout = 90 }
    elseif ($source.Strategy -match "pdf_docling") { $timeout = 120 }
    elseif ($source.Strategy -match "html|reader|static") { $timeout = 60 }

    Write-Host "[$id] prepare $prepareInput"
    $prepare = Invoke-PrepareIngest -InputPath $prepareInput -Id $id -TimeoutSeconds $timeout
    $prepStatus = "hard_fail"
    $documentPath = $null
    $documentChars = 0
    $documentRejectHits = @()
    $counts = $null
    $errors = @()
    $warnings = @()
    $titleGateStatus = "pending_ingest_metadata_support"
    $contentGateFailures = @()

    if ($prepare.parsed) {
        $prepStatus = [string]$prepare.parsed.status
        $documentPath = [string]$prepare.parsed.document_path
        $counts = $prepare.parsed.counts
        $errors = @($prepare.parsed.errors)
        $warnings = @($prepare.parsed.warnings)
        if ($documentPath -and (Test-Path $documentPath)) {
            $documentText = Get-TextIfReadable $documentPath
            $documentChars = $documentText.Length
            $documentRejectHits = Find-RejectHits -Text $documentText -Patterns $rejectPatterns
            if ($documentText.IndexOf($source.Title, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $titleGateStatus = "document_contains_expected_title"
            }
        }
    }

    if ($prepare.exit_code -ne 0 -or $prepStatus -eq "hard_fail") {
        $contentGateFailures += "prepare_failed"
    }
    if ($documentChars -lt $minChars) {
        $contentGateFailures += "document_too_short"
    }
    if ($documentRejectHits.Count -gt 0) {
        $contentGateFailures += "reject_pattern_found"
    }

    $qualityStatus = "pass"
    if ($contentGateFailures.Count -gt 0) {
        $qualityStatus = "fail"
    } elseif ($prepStatus -eq "soft_fail") {
        $qualityStatus = "soft_pass"
    }

    $prepareRows += [pscustomobject]@{
        id = $id
        prepare_status = $prepStatus
        quality_status = $qualityStatus
        content_gate_failures = $contentGateFailures
        title_gate_status = $titleGateStatus
        timeout_seconds = $timeout
        elapsed_seconds = $prepare.elapsed_seconds
        input_path = $prepareInput
        document_path = $documentPath
        document_chars = $documentChars
        reject_hits = $documentRejectHits
        counts = $counts
        warnings = $warnings
        errors = $errors
        raw_output_tail = $prepare.raw_output_tail
    }
}

Write-Jsonl -Path $SelectionPath -Rows $selectionRows
Write-Jsonl -Path $SourceReportPath -Rows $sourceRows
if (-not $SkipPrepare) {
    Write-Jsonl -Path $PrepareReportPath -Rows $prepareRows
}

$prepareSummary = $null
if (-not $SkipPrepare) {
    $prepareSummary = [pscustomobject]@{
        pass = @($prepareRows | Where-Object { $_.quality_status -eq "pass" }).Count
        soft_pass = @($prepareRows | Where-Object { $_.quality_status -eq "soft_pass" }).Count
        fail = @($prepareRows | Where-Object { $_.quality_status -eq "fail" }).Count
        hard_fail = @($prepareRows | Where-Object { $_.prepare_status -eq "hard_fail" }).Count
        pending_title_override = @($prepareRows | Where-Object { $_.title_gate_status -eq "pending_ingest_metadata_support" }).Count
    }
}

$summary = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    run_stamp = $RunStamp
    selected_count = $selectionRows.Count
    source_validation = [pscustomobject]@{
        downloaded = @($sourceRows | Where-Object { $_.validation_status -match "^downloaded" }).Count
        failed = @($sourceRows | Where-Object { $_.validation_status -eq "download_failed" }).Count
        reader_snapshot = @($sourceRows | Where-Object { $_.fallback_used -eq "reader_markdown" }).Count
        pdftotext_snapshot = @($sourceRows | Where-Object { $_.fallback_used -eq "pdftotext_markdown" }).Count
        reject_hit_rows = @($sourceRows | Where-Object { $_.reject_hits.Count -gt 0 }).Count
    }
    prepare = $prepareSummary
    reports = [pscustomobject]@{
        selection = $SelectionPath
        source_validation = $SourceReportPath
        prepare = if ($SkipPrepare) { $null } else { $PrepareReportPath }
    }
}

Write-Utf8NoBom -Path $SummaryPath -Text (($summary | ConvertTo-Json -Depth 20) + "`n")
$summary | ConvertTo-Json -Depth 20
