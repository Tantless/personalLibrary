param(
    [string]$ManifestPath = ".trellis/tasks/06-18-pkcs-m3-baseline-corpus-v1/selected-sources-v1-draft.jsonl",
    [string]$TaskDir = ".trellis/tasks/06-18-pkcs-m3-baseline-corpus-v1",
    [switch]$SkipReset,
    [string[]]$OnlyIds = @()
)

$ErrorActionPreference = "Stop"

$RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$WorkspaceRoot = (Get-Location).Path
$RunReportDir = Join-Path $TaskDir "full-reingest-$RunStamp"
$PrivateRoot = Join-Path $WorkspaceRoot "data/private/m3-baseline-v1/full"
$DownloadRoot = Join-Path $PrivateRoot "source-downloads"
$SnapshotRoot = Join-Path $PrivateRoot "snapshots"
$PrepRoot = Join-Path $PrivateRoot "ingest-prep"

$SourceReportPath = Join-Path $RunReportDir "source-validation.jsonl"
$PrepareReportPath = Join-Path $RunReportDir "prepare.jsonl"
$IngestReportPath = Join-Path $RunReportDir "ingest.jsonl"
$QualityReportPath = Join-Path $RunReportDir "quality.jsonl"
$FailureQueuePath = Join-Path $RunReportDir "failure-queue.jsonl"
$SummaryPath = Join-Path $RunReportDir "summary.json"

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
    $resolved = Resolve-OutputPath $Path
    [System.IO.File]::AppendAllText($resolved, (($Row | ConvertTo-Json -Depth 30 -Compress) + "`n"), $encoding)
}

function Clear-DirectoryContentsSafely {
    param([string]$Path)
    $resolved = (Resolve-Path $Path).Path
    $workspace = (Resolve-Path $WorkspaceRoot).Path
    $allowedPrefix = Join-Path $workspace "data"
    if (-not $resolved.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "refusing to clear path outside workspace data directory: $resolved"
    }
    if ($resolved -eq $allowedPrefix) {
        throw "refusing to clear data root directly: $resolved"
    }
    Get-ChildItem -Force -LiteralPath $resolved | Remove-Item -Recurse -Force
}

function Invoke-CurlDownload {
    param(
        [string]$Url,
        [string]$Destination,
        [int]$MaxTimeSeconds = 180
    )
    $Destination = Resolve-OutputPath $Destination
    $metadataFormat = "PKCSMETA:%{http_code}|%{content_type}|%{size_download}|%{url_effective}"
    $args = @(
        "-L",
        "--silent",
        "--show-error",
        "--connect-timeout", "20",
        "--max-time", [string]$MaxTimeSeconds,
        "-A", "Mozilla/5.0 PKCS-M3-Baseline-Full",
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
    foreach ($ext in @(".pdf", ".docx", ".html", ".htm", ".md", ".markdown", ".txt")) {
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

function New-DocxPandocMarkdown {
    param(
        [string]$DocxPath,
        [string]$MarkdownPath,
        [string]$Title,
        [string]$Url
    )
    $pandoc = Get-Command pandoc -ErrorAction Stop
    & $pandoc.Source -f docx -t gfm --wrap=none -o (Resolve-OutputPath $MarkdownPath) (Resolve-OutputPath $DocxPath)
    if ($LASTEXITCODE -ne 0) {
        throw "pandoc docx conversion failed for $DocxPath"
    }
    $text = [System.IO.File]::ReadAllText((Resolve-OutputPath $MarkdownPath), [System.Text.Encoding]::UTF8)
    if ($text -notmatch "(?m)^#\s+") {
        Write-Utf8NoBom -Path $MarkdownPath -Text ("# $Title`n`nSource URL: $Url`n`n$text")
    }
    return Resolve-OutputPath $MarkdownPath
}

function New-HtmlPandocMarkdown {
    param(
        [string]$HtmlPath,
        [string]$MarkdownPath,
        [string]$Title,
        [string]$Url
    )
    $pandoc = Get-Command pandoc -ErrorAction Stop
    & $pandoc.Source -f html -t gfm --wrap=none -o (Resolve-OutputPath $MarkdownPath) (Resolve-OutputPath $HtmlPath)
    if ($LASTEXITCODE -ne 0) {
        throw "pandoc html conversion failed for $HtmlPath"
    }
    $text = [System.IO.File]::ReadAllText((Resolve-OutputPath $MarkdownPath), [System.Text.Encoding]::UTF8)
    Write-Utf8NoBom -Path $MarkdownPath -Text ("# $Title`n`nSource URL: $Url`n`n$text")
    return Resolve-OutputPath $MarkdownPath
}

function New-Utf8SanitizedMarkdown {
    param(
        [string]$InputPath,
        [string]$MarkdownPath,
        [string]$Title,
        [string]$Url
    )
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-OutputPath $InputPath))
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    if ($text -notmatch "(?m)^#\s+") {
        $text = "# $Title`n`nSource URL: $Url`n`n$text"
    }
    Write-Utf8NoBom -Path $MarkdownPath -Text $text
    return Resolve-OutputPath $MarkdownPath
}

function Invoke-PrepareIngest {
    param(
        [string]$InputPath,
        [string]$Id,
        [int]$TimeoutSeconds
    )
    $slug = "v1-full-$($Id.ToLowerInvariant())-$RunStamp"
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

function Invoke-PkcsIngest {
    param(
        [string]$DocumentPath,
        [string]$CanonicalKey
    )
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $output = & ".venv/Scripts/pkcs.exe" ingest $DocumentPath --knowledge-type document --canonical-key $CanonicalKey 2>&1
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

function Get-PrepareTimeout {
    param([string]$Strategy, [string]$InputPath)
    $ext = [System.IO.Path]::GetExtension($InputPath).ToLowerInvariant()
    if ($Strategy -match "docx" -or $ext -eq ".docx") { return 90 }
    if ($Strategy -match "pdf_docling" -or $ext -eq ".pdf") { return 120 }
    if ($Strategy -match "html|reader|static" -or $ext -in @(".html", ".htm")) { return 30 }
    return 30
}

function Set-ManifestTitleHeading {
    param(
        [string]$DocumentPath,
        [string]$ExpectedTitle,
        [string]$Url,
        [string]$Id,
        [string]$CanonicalKey
    )
    $resolved = Resolve-OutputPath $DocumentPath
    $text = [System.IO.File]::ReadAllText($resolved, [System.Text.Encoding]::UTF8)
    $firstHeading = $null
    foreach ($line in $text -split "`r?`n") {
        if ($line -match "^#\s+(.+?)\s*$") {
            $firstHeading = $Matches[1]
            break
        }
    }
    if ($firstHeading -and $firstHeading.Trim() -eq $ExpectedTitle.Trim()) {
        return [pscustomobject]@{ applied = $false; previous_title = $firstHeading }
    }

    $prefix = "# $ExpectedTitle`n`nSource URL: $Url`nCorpus ID: $Id`nCanonical Key: $CanonicalKey`n`n"
    Write-Utf8NoBom -Path $resolved -Text ($prefix + $text)
    return [pscustomobject]@{ applied = $true; previous_title = $firstHeading }
}

function New-Batches {
    param([array]$Rows)
    $batches = @()
    $current = @()
    $heavyCount = 0
    foreach ($row in $Rows) {
        $source = Get-EffectiveSource $row
        $isHeavy = ($source.Strategy -match "pdf_docling|docx_docling|xlsx") -or ($source.Format -in @("pdf", "docx", "xlsx"))
        if ($current.Count -gt 0 -and ($current.Count -ge 20 -or ($isHeavy -and $heavyCount -ge 5))) {
            $batches += ,$current
            $current = @()
            $heavyCount = 0
        }
        $current += $row
        if ($isHeavy) {
            $heavyCount += 1
        }
    }
    if ($current.Count -gt 0) {
        $batches += ,$current
    }
    return $batches
}

function Get-DbTableCounts {
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

function Get-DbSourceTitles {
    $sql = "select canonical_key, title from sources order by canonical_key;"
    $output = docker exec pkcs-postgres psql -U pkcs -d pkcs -t -A -F "`t" -c $sql
    $titles = @{}
    foreach ($line in $output) {
        if (-not $line.Trim()) { continue }
        $parts = $line.Split("`t", 2)
        if ($parts.Count -eq 2) {
            $titles[$parts[0]] = $parts[1]
        }
    }
    return $titles
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

New-Item -ItemType Directory -Force -Path $RunReportDir | Out-Null

Write-Host "[preflight] docker compose up"
docker compose up -d | Out-Host
Write-Host "[preflight] pkcs health"
& ".venv/Scripts/pkcs.exe" health | Out-Host

$manifestRows = @()
foreach ($line in Get-Content $ManifestPath -Encoding UTF8) {
    if (-not $line.Trim()) { continue }
    $manifestRows += ($line | ConvertFrom-Json)
}
if ($OnlyIds.Count -gt 0) {
    $manifestRows = @($manifestRows | Where-Object { $OnlyIds -contains $_.id })
}
if ($manifestRows.Count -eq 0) {
    throw "manifest produced no rows"
}

if (-not $SkipReset) {
    Write-Host "[reset] clearing PKCS database tables"
    $truncateSql = "truncate table image_artifacts, table_artifacts, citations, chunks, source_versions, sources, ingest_jobs, source_key_counters restart identity cascade;"
    docker exec pkcs-postgres psql -U pkcs -d pkcs -v ON_ERROR_STOP=1 -c $truncateSql | Out-Host

    Write-Host "[reset] clearing data/raw and data/private contents"
    foreach ($dir in @("data/raw", "data/private")) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
        }
        Clear-DirectoryContentsSafely -Path $dir
    }
}

New-Item -ItemType Directory -Force -Path $DownloadRoot, $SnapshotRoot, $PrepRoot | Out-Null

$batches = New-Batches -Rows $manifestRows
$batchIndex = 0
$allQualityRows = @()

foreach ($batch in $batches) {
    $batchIndex += 1
    Write-Host "[batch $batchIndex/$($batches.Count)] rows=$($batch.Count)"
    foreach ($row in $batch) {
        $source = Get-EffectiveSource $row
        $gate = $row.minimum_quality_gate
        $minChars = [int]$gate.min_document_chars
        $rejectPatterns = @($gate.reject_patterns)
        $id = [string]$row.id
        $safeName = $id.ToLowerInvariant()
        $ext = Get-DownloadExtension -Format $source.Format -Url $source.Url -Strategy $source.Strategy
        $downloadPath = Join-Path $DownloadRoot "$safeName$ext"

        Write-Host "[$id] download"
        $download = Invoke-CurlDownload -Url $source.Url -Destination $downloadPath -MaxTimeSeconds 180
        $text = Get-TextIfReadable $download.destination
        $isHtmlDownload = (($download.content_type -and $download.content_type.ToLowerInvariant().Contains("html")) -or $text.TrimStart().StartsWith("<!DOCTYPE html", [System.StringComparison]::OrdinalIgnoreCase) -or $text.TrimStart().StartsWith("<html", [System.StringComparison]::OrdinalIgnoreCase))
        if ($isHtmlDownload -and ([System.IO.Path]::GetExtension($download.destination).ToLowerInvariant() -notin @(".html", ".htm"))) {
            $htmlPath = Join-Path $DownloadRoot "$safeName.html"
            Move-Item -Force -Path $download.destination -Destination $htmlPath
            $download.destination = Resolve-OutputPath $htmlPath
            $text = Get-TextIfReadable $download.destination
        }
        $rejectHits = Find-RejectHits -Text $text -Patterns $rejectPatterns
        $validationStatus = "downloaded"
        if ($download.exit_code -ne 0 -or -not ($download.http_code -match "^2")) {
            $validationStatus = "download_failed"
        }

        $prepareInput = $download.destination
        $fallbackUsed = $null
        $sourceFailure = $null

        if ($validationStatus -eq "download_failed") {
            $sourceFailure = "download_failed"
        } elseif ($source.Strategy -eq "pdf_text_only_pdftotext") {
            $snapshotPath = Join-Path $SnapshotRoot "$safeName.pdftotext.md"
            $prepareInput = New-PdfTextMarkdown -PdfPath $download.destination -MarkdownPath $snapshotPath -Title $source.Title -Url $source.Url
            $text = Get-TextIfReadable $prepareInput
            $rejectHits = Find-RejectHits -Text $text -Patterns $rejectPatterns
            $fallbackUsed = "pdftotext_markdown"
        } elseif ($source.Strategy -eq "docx_pandoc_markdown_snapshot") {
            $snapshotPath = Join-Path $SnapshotRoot "$safeName.pandoc.md"
            $prepareInput = New-DocxPandocMarkdown -DocxPath $download.destination -MarkdownPath $snapshotPath -Title $source.Title -Url $source.Url
            $text = Get-TextIfReadable $prepareInput
            $rejectHits = Find-RejectHits -Text $text -Patterns $rejectPatterns
            $fallbackUsed = "docx_pandoc_markdown"
        } elseif ($source.Strategy -eq "markdown_utf8_sanitized") {
            $snapshotPath = Join-Path $SnapshotRoot "$safeName.utf8.md"
            $prepareInput = New-Utf8SanitizedMarkdown -InputPath $download.destination -MarkdownPath $snapshotPath -Title $source.Title -Url $source.Url
            $text = Get-TextIfReadable $prepareInput
            $rejectHits = Find-RejectHits -Text $text -Patterns $rejectPatterns
            $fallbackUsed = "markdown_utf8_sanitized"
        } elseif ($isHtmlDownload -and $source.Url -notmatch "raw\.githubusercontent\.com") {
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

        $sourceReport = [pscustomobject]@{
            id = $id
            batch_index = $batchIndex
            canonical_key = $row.canonical_key
            url = $source.Url
            format = $source.Format
            strategy = $source.Strategy
            quality_tier = $row.quality_tier
            decision = $row.decision
            validation_status = $validationStatus
            http_code = $download.http_code
            content_type = $download.content_type
            size_download = $download.size_download
            source_path = $download.destination
            prepare_input_path = $prepareInput
            fallback_used = $fallbackUsed
            readable_chars = $text.Length
            reject_hits = $rejectHits
            failure = $sourceFailure
        }
        Add-JsonlRow -Path $SourceReportPath -Row $sourceReport

        if ($sourceFailure) {
            Add-JsonlRow -Path $FailureQueuePath -Row ([pscustomobject]@{ id = $id; step = "source_validation"; failure = $sourceFailure; url = $source.Url })
            continue
        }

        Write-Host "[$id] prepare"
        $timeout = Get-PrepareTimeout -Strategy $source.Strategy -InputPath $prepareInput
        $prepare = Invoke-PrepareIngest -InputPath $prepareInput -Id $id -TimeoutSeconds $timeout

        if ($prepare.parsed -and $prepare.parsed.status -eq "hard_fail" -and ([System.IO.Path]::GetExtension($prepareInput).ToLowerInvariant() -in @(".html", ".htm"))) {
            $snapshotPath = Join-Path $SnapshotRoot "$safeName.pandoc-html.md"
            $prepareInput = New-HtmlPandocMarkdown -HtmlPath $download.destination -MarkdownPath $snapshotPath -Title $source.Title -Url $source.Url
            $fallbackUsed = "html_pandoc_markdown_after_docling_fail"
            $timeout = 30
            $prepare = Invoke-PrepareIngest -InputPath $prepareInput -Id $id -TimeoutSeconds $timeout
        }

        $prepStatus = "hard_fail"
        $documentPath = $null
        $documentChars = 0
        $documentRejectHits = @()
        $counts = $null
        $warnings = @()
        $errors = @()
        $titleOverride = $null
        if ($prepare.parsed) {
            $prepStatus = [string]$prepare.parsed.status
            $documentPath = [string]$prepare.parsed.document_path
            $counts = $prepare.parsed.counts
            $warnings = @($prepare.parsed.warnings)
            $errors = @($prepare.parsed.errors)
            if ($documentPath -and (Test-Path $documentPath)) {
                $titleOverride = Set-ManifestTitleHeading -DocumentPath $documentPath -ExpectedTitle $source.Title -Url $source.Url -Id $id -CanonicalKey $row.canonical_key
                $documentText = Get-TextIfReadable $documentPath
                $documentChars = $documentText.Length
                $documentRejectHits = Find-RejectHits -Text $documentText -Patterns $rejectPatterns
            }
        }

        $prepareReport = [pscustomobject]@{
            id = $id
            batch_index = $batchIndex
            prepare_status = $prepStatus
            timeout_seconds = $timeout
            elapsed_seconds = $prepare.elapsed_seconds
            input_path = $prepareInput
            document_path = $documentPath
            document_chars = $documentChars
            reject_hits = $documentRejectHits
            counts = $counts
            warnings = $warnings
            errors = $errors
            fallback_used = $fallbackUsed
            title_override = $titleOverride
            raw_output_tail = $prepare.raw_output_tail
        }
        Add-JsonlRow -Path $PrepareReportPath -Row $prepareReport

        if ($prepare.exit_code -ne 0 -or $prepStatus -eq "hard_fail" -or -not $documentPath -or -not (Test-Path $documentPath)) {
            Add-JsonlRow -Path $FailureQueuePath -Row ([pscustomobject]@{ id = $id; step = "prepare"; failure = $prepStatus; errors = $errors })
            continue
        }

        Write-Host "[$id] ingest"
        $ingest = Invoke-PkcsIngest -DocumentPath $documentPath -CanonicalKey $row.canonical_key
        $ingestStatus = $null
        $sourceId = $null
        $versionId = $null
        $chunksCreated = 0
        $ingestErrors = @()
        if ($ingest.parsed) {
            $ingestStatus = [string]$ingest.parsed.status
            $sourceId = [string]$ingest.parsed.source_id
            $versionId = [string]$ingest.parsed.version_id
            $chunksCreated = [int]$ingest.parsed.chunks_created
            $ingestErrors = @($ingest.parsed.failed)
        }
        $ingestReport = [pscustomobject]@{
            id = $id
            batch_index = $batchIndex
            exit_code = $ingest.exit_code
            ingest_status = $ingestStatus
            elapsed_seconds = $ingest.elapsed_seconds
            source_id = $sourceId
            version_id = $versionId
            canonical_key = $row.canonical_key
            chunks_created = $chunksCreated
            errors = $ingestErrors
            raw_output_tail = $ingest.raw_output_tail
        }
        Add-JsonlRow -Path $IngestReportPath -Row $ingestReport

        $qualityFailures = @()
        $ingestSucceeded = ($ingest.exit_code -eq 0 -and $ingestStatus -in @("completed", "succeeded") -and $sourceId)
        if (-not $ingestSucceeded) { $qualityFailures += "ingest_failed" }
        if ($documentChars -lt $minChars) { $qualityFailures += "document_too_short" }
        if ($documentRejectHits.Count -gt 0) { $qualityFailures += "reject_pattern_found" }
        if ($chunksCreated -lt [int]$gate.min_chunks) { $qualityFailures += "too_few_chunks" }
        if ($row.minimum_quality_gate.require_local_artifact -eq $true) {
            $localArtifactCount = 0
            if ($counts) {
                $localArtifactCount = [int]$counts.local_images + [int]$counts.inline_tables + [int]$counts.sidecar_tables
            }
            if ($localArtifactCount -le 0) { $qualityFailures += "local_artifact_required_but_missing" }
        }

        $searchSmoke = Invoke-SearchSmoke -Row $row
        if (-not $searchSmoke.passed) {
            $qualityFailures += "search_smoke_failed"
        }

        $qualityStatus = "pass"
        if ($qualityFailures.Count -gt 0) {
            $qualityStatus = "fail"
        } elseif ($prepStatus -eq "soft_fail") {
            $qualityStatus = "soft_pass"
        }

        $qualityRow = [pscustomobject]@{
            id = $id
            batch_index = $batchIndex
            quality_status = $qualityStatus
            failures = $qualityFailures
            expected_title = $source.Title
            document_chars = $documentChars
            chunks_created = $chunksCreated
            quality_tier = $row.quality_tier
            fallback_used = $fallbackUsed
            search_smoke = $searchSmoke
            counts = $counts
        }
        Add-JsonlRow -Path $QualityReportPath -Row $qualityRow
        $allQualityRows += $qualityRow

        if ($qualityStatus -eq "fail") {
            Add-JsonlRow -Path $FailureQueuePath -Row ([pscustomobject]@{ id = $id; step = "quality_gate"; failures = $qualityFailures })
        }
    }
}

$dbCounts = Get-DbTableCounts
$dbTitles = Get-DbSourceTitles
$titleMismatches = @()
foreach ($row in $manifestRows) {
    $source = Get-EffectiveSource $row
    if ($dbTitles.ContainsKey($row.canonical_key)) {
        if ($dbTitles[$row.canonical_key] -ne $source.Title) {
            $titleMismatches += [pscustomobject]@{
                id = $row.id
                canonical_key = $row.canonical_key
                expected = $source.Title
                actual = $dbTitles[$row.canonical_key]
            }
        }
    } else {
        $titleMismatches += [pscustomobject]@{
            id = $row.id
            canonical_key = $row.canonical_key
            expected = $source.Title
            actual = $null
        }
    }
}

$failureRows = @()
if (Test-Path $FailureQueuePath) {
    $failureRows = @(Get-Content $FailureQueuePath -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}

$summary = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    run_stamp = $RunStamp
    manifest_count = $manifestRows.Count
    batches = $batches.Count
    db_counts = $dbCounts
    quality = [pscustomobject]@{
        pass = @($allQualityRows | Where-Object { $_.quality_status -eq "pass" }).Count
        soft_pass = @($allQualityRows | Where-Object { $_.quality_status -eq "soft_pass" }).Count
        fail = @($allQualityRows | Where-Object { $_.quality_status -eq "fail" }).Count
        search_smoke_pass = @($allQualityRows | Where-Object { $_.search_smoke.passed }).Count
        title_mismatches = $titleMismatches.Count
    }
    fallback = [pscustomobject]@{
        reader_markdown = @($allQualityRows | Where-Object { $_.fallback_used -eq "reader_markdown" }).Count
        pdftotext_markdown = @($allQualityRows | Where-Object { $_.fallback_used -eq "pdftotext_markdown" }).Count
        docx_pandoc_markdown = @($allQualityRows | Where-Object { $_.fallback_used -eq "docx_pandoc_markdown" }).Count
        html_pandoc_markdown_after_docling_fail = @($allQualityRows | Where-Object { $_.fallback_used -eq "html_pandoc_markdown_after_docling_fail" }).Count
    }
    failure_count = $failureRows.Count
    title_mismatches = $titleMismatches
    reports = [pscustomobject]@{
        source_validation = $SourceReportPath
        prepare = $PrepareReportPath
        ingest = $IngestReportPath
        quality = $QualityReportPath
        failure_queue = $FailureQueuePath
    }
}

Write-Utf8NoBom -Path $SummaryPath -Text (($summary | ConvertTo-Json -Depth 30) + "`n")
$summary | ConvertTo-Json -Depth 30
