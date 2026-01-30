# Final optimized version: Manual walk + parallel copy
# Based on diagnostics: Manual walk is 100x faster than -Recurse on network shares
# Usage: .\copy-sample-pairs-final.ps1 [-SampleSize 200]

param(
    [int]$SampleSize = 200
)

$sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"
$destRoot = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"

Write-Host "=== Optimized Sample Copier (Manual Walk) ===" -ForegroundColor Cyan
Write-Host "Source: $sourceRoot" -ForegroundColor Gray
Write-Host "Destination: $destRoot" -ForegroundColor Gray
Write-Host "Target: $SampleSize files" -ForegroundColor Gray
Write-Host ""

# Create destination
if (-not (Test-Path $destRoot)) {
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
}

# Phase 1: Collect file paths (manual walk - FAST on network shares)
Write-Host "Phase 1: Finding DCM files..." -ForegroundColor Yellow
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

$dcmFiles = @()
$casesScanned = 0
$lastUpdate = Get-Date

# Get case folders - do this once
Write-Host "Enumerating case folders..." -ForegroundColor Gray
$caseFolders = Get-ChildItem -Path $sourceRoot -Directory -ErrorAction SilentlyContinue
Write-Host "Found $($caseFolders.Count) case folders" -ForegroundColor Green
Write-Host ""

foreach ($caseFolder in $caseFolders) {
    $casesScanned++

    # Progress every 2 seconds
    $now = Get-Date
    if (($now - $lastUpdate).TotalSeconds -ge 2) {
        $elapsed = $stopwatch.Elapsed.TotalSeconds
        $rate = $casesScanned / $elapsed
        Write-Host "`r  Scanned $casesScanned cases, found $($dcmFiles.Count) files ($($rate.ToString('F1')) cases/sec)..." -NoNewline -ForegroundColor Yellow
        $lastUpdate = $now
    }

    # Check for Scans folder
    $scansPath = Join-Path $caseFolder.FullName "Scans"

    if (Test-Path $scansPath) {
        # Get subdirectories (Lower, Upper, Misc, etc.)
        $scanSubdirs = Get-ChildItem -Path $scansPath -Directory -ErrorAction SilentlyContinue

        foreach ($subdir in $scanSubdirs) {
            # Get all DCM files
            $dcms = Get-ChildItem -Path $subdir.FullName -Filter "*.dcm" -File -ErrorAction SilentlyContinue

            foreach ($dcm in $dcms) {
                $dcmFiles += $dcm

                if ($dcmFiles.Count -ge $SampleSize) {
                    Write-Host "`r" -NoNewline
                    break
                }
            }

            if ($dcmFiles.Count -ge $SampleSize) { break }
        }
    }

    if ($dcmFiles.Count -ge $SampleSize) { break }
}

$stopwatch.Stop()

Write-Host "`r" -NoNewline
Write-Host "Found $($dcmFiles.Count) files in $($stopwatch.Elapsed.TotalSeconds.ToString('F1'))s (scanned $casesScanned/$($caseFolders.Count) cases)" -ForegroundColor Green
Write-Host ""

if ($dcmFiles.Count -eq 0) {
    Write-Host "ERROR: No DCM files found!" -ForegroundColor Red
    exit 1
}

# Randomly select if we found more than needed
$selected = $dcmFiles
if ($dcmFiles.Count -gt $SampleSize) {
    Write-Host "Randomly selecting $SampleSize from $($dcmFiles.Count) files..." -ForegroundColor Yellow
    $selected = $dcmFiles | Get-Random -Count $SampleSize
}

# Phase 2: Copy files (parallel on PS7+)
Write-Host ""
Write-Host "Phase 2: Copying $($selected.Count) files..." -ForegroundColor Yellow

$copyStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$psVersion = $PSVersionTable.PSVersion.Major

if ($psVersion -ge 7) {
    Write-Host "Using parallel copy (4 threads)..." -ForegroundColor Gray

    $results = $selected | ForEach-Object -Parallel {
        $dcmFile = $_
        $sourceRoot = $using:sourceRoot
        $destRoot = $using:destRoot

        # Generate unique name
        $pathParts = $dcmFile.DirectoryName.Replace($sourceRoot, "").Trim('\').Split('\')
        $caseName = $pathParts[0]
        $scanType = $pathParts[-1]
        $uniqueName = "${caseName}_${scanType}_$($dcmFile.Name)"

        if ($uniqueName.Length -gt 200) {
            $hash = [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($dcmFile.FullName))).Replace("-", "").Substring(0, 8)
            $uniqueName = "${hash}_$($dcmFile.Name)"
        }

        $destDcmPath = Join-Path $destRoot $uniqueName
        $destStlPath = $destDcmPath -replace '\.dcm$', '.stl'
        $sourceStlPath = Join-Path $dcmFile.DirectoryName ($dcmFile.BaseName + ".stl")
        $hasStl = Test-Path $sourceStlPath

        try {
            Copy-Item -Path $dcmFile.FullName -Destination $destDcmPath -Force
            if ($hasStl) {
                Copy-Item -Path $sourceStlPath -Destination $destStlPath -Force
            }
            return @{Success=$true; HasStl=$hasStl}
        } catch {
            return @{Success=$false; Error=$_.Exception.Message}
        }
    } -ThrottleLimit 4

    $withStl = ($results | Where-Object { $_.Success -and $_.HasStl }).Count
    $withoutStl = ($results | Where-Object { $_.Success -and -not $_.HasStl }).Count
    $errors = ($results | Where-Object { -not $_.Success }).Count

} else {
    Write-Host "Using sequential copy (PS 5.x)..." -ForegroundColor Gray

    $copied = 0
    $withStl = 0
    $withoutStl = 0

    foreach ($dcmFile in $selected) {
        $copied++

        $pathParts = $dcmFile.DirectoryName.Replace($sourceRoot, "").Trim('\').Split('\')
        $caseName = $pathParts[0]
        $scanType = $pathParts[-1]
        $uniqueName = "${caseName}_${scanType}_$($dcmFile.Name)"

        if ($uniqueName.Length -gt 200) {
            $hash = [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($dcmFile.FullName))).Replace("-", "").Substring(0, 8)
            $uniqueName = "${hash}_$($dcmFile.Name)"
        }

        $destDcmPath = Join-Path $destRoot $uniqueName
        $destStlPath = $destDcmPath -replace '\.dcm$', '.stl'
        $sourceStlPath = Join-Path $dcmFile.DirectoryName ($dcmFile.BaseName + ".stl")
        $hasStl = Test-Path $sourceStlPath

        try {
            Copy-Item -Path $dcmFile.FullName -Destination $destDcmPath -Force
            if ($hasStl) {
                Copy-Item -Path $sourceStlPath -Destination $destStlPath -Force
                $withStl++
            } else {
                $withoutStl++
            }

            if ($copied % 20 -eq 0) {
                Write-Host "`r  [$copied/$($selected.Count)] Pairs: $withStl, DCM-only: $withoutStl" -NoNewline -ForegroundColor Cyan
            }
        } catch {
            Write-Host "`nERROR: $_" -ForegroundColor Red
        }
    }
    Write-Host ""
}

$copyStopwatch.Stop()

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Find time: $($stopwatch.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Gray
Write-Host "Copy time: $($copyStopwatch.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Gray
Write-Host "Total time: $($($stopwatch.Elapsed.TotalSeconds + $copyStopwatch.Elapsed.TotalSeconds).ToString('F1'))s" -ForegroundColor Gray
Write-Host ""
Write-Host "Files copied: $($selected.Count)" -ForegroundColor Green
Write-Host "  With STL: $withStl pairs" -ForegroundColor Green
Write-Host "  DCM only: $withoutStl (need conversion)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Destination: $destRoot" -ForegroundColor Gray

$finalDcm = (Get-ChildItem -Path $destRoot -Filter "*.dcm").Count
$finalStl = (Get-ChildItem -Path $destRoot -Filter "*.stl").Count
Write-Host "Final count: $finalDcm DCM, $finalStl STL" -ForegroundColor Gray

if ($withoutStl -gt 0) {
    Write-Host ""
    Write-Host "Next step: .\scripts\convert-missing-stls.ps1" -ForegroundColor Yellow
}
