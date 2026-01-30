# Ultra-fast copier using robocopy list + PowerShell copy
# Robocopy is much faster at listing files on network shares
# Usage: .\copy-sample-pairs-robocopy.ps1 [-SampleSize 200]

param(
    [int]$SampleSize = 200
)

$sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"
$destRoot = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"

Write-Host "=== Ultra-Fast Copier (Robocopy Method) ===" -ForegroundColor Cyan
Write-Host "Source: $sourceRoot" -ForegroundColor Gray
Write-Host "Destination: $destRoot" -ForegroundColor Gray
Write-Host "Target: $SampleSize files" -ForegroundColor Gray
Write-Host ""

# Create destination
if (-not (Test-Path $destRoot)) {
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
}

# Phase 1: Use robocopy to list all DCM files (MUCH faster on network)
Write-Host "Phase 1: Listing DCM files with robocopy (this is fast)..." -ForegroundColor Yellow
$listTimer = [System.Diagnostics.Stopwatch]::StartNew()

$tempList = Join-Path $env:TEMP "dcm_files_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"

# Robocopy list mode - lists files without copying
# /L = list only, /S = subdirs, /FP = full path, /NJH = no job header, /NJS = no job summary
Write-Host "  Running robocopy to enumerate files..." -ForegroundColor Gray
Write-Host "  (This scans the entire share but is optimized for network - may take 2-5 min)" -ForegroundColor DarkGray

$robocopyOutput = robocopy "$sourceRoot" "C:\NUL" "*.dcm" /L /S /FP /NJH /NJS /NDL /NC /BYTES /TS 2>&1

# Parse robocopy output to extract file paths
$dcmPaths = @()
foreach ($line in $robocopyOutput) {
    # Robocopy output lines with full paths contain the source root
    if ($line -match [regex]::Escape($sourceRoot) -and $line -match '\.dcm$') {
        # Extract just the path part (robocopy output format varies)
        if ($line -match '\s+([A-Za-z]:\\.*\.dcm)$' -or $line -match '\s+(\\\\.*\.dcm)$') {
            $fullPath = $matches[1].Trim()
            # Only include files in Scans folders
            if ($fullPath -like "*\Scans\*") {
                $dcmPaths += $fullPath

                # Stop early if we have enough
                if ($dcmPaths.Count -ge $SampleSize * 2) {
                    Write-Host "`r  Found $($dcmPaths.Count) DCM files (enough to sample from)..." -NoNewline -ForegroundColor Yellow
                    break
                }

                if ($dcmPaths.Count % 100 -eq 0) {
                    Write-Host "`r  Found $($dcmPaths.Count) DCM files..." -NoNewline -ForegroundColor Yellow
                }
            }
        }
    }
}

$listTimer.Stop()

Write-Host "`r" -NoNewline
Write-Host "  ✓ Found $($dcmPaths.Count) DCM files in $($listTimer.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Green
Write-Host ""

if ($dcmPaths.Count -eq 0) {
    Write-Host "ERROR: Robocopy didn't find any DCM files!" -ForegroundColor Red
    Write-Host "Trying alternative parsing..." -ForegroundColor Yellow

    # Alternative: save robocopy output to file for debugging
    $robocopyOutput | Out-File $tempList
    Write-Host "Robocopy output saved to: $tempList" -ForegroundColor Gray
    Write-Host "Please check the file to see what robocopy found." -ForegroundColor Gray
    exit 1
}

# Random selection
Write-Host "Phase 2: Selecting random sample..." -ForegroundColor Yellow
$selectTimer = [System.Diagnostics.Stopwatch]::StartNew()

$selected = $dcmPaths
if ($dcmPaths.Count -gt $SampleSize) {
    $selected = $dcmPaths | Get-Random -Count $SampleSize
}

$selectTimer.Stop()
Write-Host "  ✓ Selected $($selected.Count) files in $($selectTimer.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Green
Write-Host ""

# Phase 3: Copy selected files
Write-Host "Phase 3: Copying $($selected.Count) files..." -ForegroundColor Yellow
$copyTimer = [System.Diagnostics.Stopwatch]::StartNew()

$withStl = 0
$withoutStl = 0
$copied = 0

foreach ($dcmPath in $selected) {
    $copied++

    # Generate unique name
    $relativePath = $dcmPath.Replace($sourceRoot, "").TrimStart('\')
    $pathParts = $relativePath.Split('\')
    $caseName = $pathParts[0]
    $scanType = $pathParts[-2]  # Parent folder (Upper/Lower/etc)
    $fileName = Split-Path $dcmPath -Leaf
    $uniqueName = "${caseName}_${scanType}_${fileName}"

    if ($uniqueName.Length -gt 200) {
        $hash = [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($dcmPath))).Replace("-", "").Substring(0, 8)
        $uniqueName = "${hash}_${fileName}"
    }

    $destDcmPath = Join-Path $destRoot $uniqueName
    $destStlPath = $destDcmPath -replace '\.dcm$', '.stl'

    # Check for STL
    $sourceDir = Split-Path $dcmPath -Parent
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($dcmPath)
    $sourceStlPath = Join-Path $sourceDir "$baseName.stl"
    $hasStl = Test-Path $sourceStlPath

    try {
        Copy-Item -Path $dcmPath -Destination $destDcmPath -Force

        if ($hasStl) {
            Copy-Item -Path $sourceStlPath -Destination $destStlPath -Force
            $withStl++
        } else {
            $withoutStl++
        }

        if ($copied % 20 -eq 0) {
            $elapsed = $copyTimer.Elapsed.TotalSeconds
            $rate = $copied / $elapsed
            Write-Host "`r  [$copied/$($selected.Count)] Copied ($(($rate * 60).ToString('F0')) files/min)..." -NoNewline -ForegroundColor Cyan
        }
    } catch {
        Write-Host "`nERROR copying $fileName: $_" -ForegroundColor Red
    }
}

$copyTimer.Stop()

Write-Host "`r" -NoNewline
Write-Host "  ✓ Copied $copied files in $($copyTimer.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Green
Write-Host ""

# Summary
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Timing:" -ForegroundColor Yellow
Write-Host "  List files (robocopy):  $($listTimer.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Gray
Write-Host "  Select random:          $($selectTimer.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Gray
Write-Host "  Copy files:             $($copyTimer.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Gray
$totalTime = $listTimer.Elapsed.TotalSeconds + $selectTimer.Elapsed.TotalSeconds + $copyTimer.Elapsed.TotalSeconds
Write-Host "  TOTAL:                  $($totalTime.ToString('F1'))s ($($($totalTime/60).ToString('F1')) min)" -ForegroundColor Green
Write-Host ""
Write-Host "Results:" -ForegroundColor Yellow
Write-Host "  Files copied: $copied" -ForegroundColor Gray
Write-Host "  With STL: $withStl pairs" -ForegroundColor Green
Write-Host "  DCM only: $withoutStl" -ForegroundColor Yellow
Write-Host ""
Write-Host "Destination: $destRoot" -ForegroundColor Gray

$finalDcm = (Get-ChildItem -Path $destRoot -Filter "*.dcm").Count
$finalStl = (Get-ChildItem -Path $destRoot -Filter "*.stl").Count
Write-Host "Final count: $finalDcm DCM, $finalStl STL" -ForegroundColor Gray

if ($withoutStl -gt 0) {
    Write-Host ""
    Write-Host "Next: .\scripts\convert-missing-stls.ps1" -ForegroundColor Yellow
}
