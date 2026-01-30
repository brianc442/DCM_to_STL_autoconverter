# Ultra-fast copier using single recursive search
# Much faster on network shares than folder-by-folder scanning
# Usage: .\copy-sample-pairs-fast-v3.ps1 [-SampleSize 200]

param(
    [int]$SampleSize = 200
)

$sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"
$destRoot = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"

Write-Host "=== Ultra-Fast Sample Copier v3 ===" -ForegroundColor Cyan
Write-Host "Source: $sourceRoot" -ForegroundColor Gray
Write-Host "Destination: $destRoot" -ForegroundColor Gray
Write-Host "Target: $SampleSize files" -ForegroundColor Gray
Write-Host ""

# Create destination
if (-not (Test-Path $destRoot)) {
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
}

Write-Host "Searching with optimized pattern (this will be much faster)..." -ForegroundColor Yellow
Write-Host "Looking for: */Scans/*/*.dcm" -ForegroundColor Gray
Write-Host ""

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

# Use optimized search - Get-ChildItem with specific depth and pattern
# This is MUCH faster than checking each folder individually
$dcmFiles = @()
$filesFound = 0

# Search for DCM files in the specific pattern: [Case]/Scans/[Type]/*.dcm
# Using -Depth 3 limits how deep it searches, making it faster
try {
    Write-Host "Scanning (this may take 2-5 minutes for first $SampleSize files)..." -ForegroundColor Yellow

    # Stream results instead of collecting all at once
    Get-ChildItem -Path $sourceRoot -Filter "*.dcm" -Recurse -Depth 3 -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            # Only take files in the Scans folder structure
            if ($_.DirectoryName -like "*\Scans\*") {
                $dcmFiles += $_
                $filesFound++

                # Show progress
                if ($filesFound % 20 -eq 0) {
                    $elapsed = $stopwatch.Elapsed.TotalSeconds
                    $rate = $filesFound / $elapsed
                    Write-Host "`rFound $filesFound DCM files in $($elapsed.ToString('F1'))s ($($rate.ToString('F1')) files/sec)..." -NoNewline -ForegroundColor Yellow
                }

                # Stop once we have enough
                if ($filesFound -ge $SampleSize) {
                    Write-Host "`r" -NoNewline
                    return
                }
            }
        }
} catch {
    Write-Host "`nWarning: Search interrupted or limited by permissions" -ForegroundColor Yellow
}

$stopwatch.Stop()

Write-Host "`r" -NoNewline
Write-Host "Found $($dcmFiles.Count) DCM files in $($stopwatch.Elapsed.TotalMinutes.ToString('F1')) minutes" -ForegroundColor Green
Write-Host ""

if ($dcmFiles.Count -eq 0) {
    Write-Host "ERROR: No DCM files found!" -ForegroundColor Red
    exit 1
}

# Take what we need
$selected = $dcmFiles
if ($dcmFiles.Count -gt $SampleSize) {
    Write-Host "Randomly selecting $SampleSize from $($dcmFiles.Count) files..." -ForegroundColor Yellow
    $selected = $dcmFiles | Get-Random -Count $SampleSize
} else {
    $selected = $dcmFiles
}

Write-Host "Copying $($selected.Count) files..." -ForegroundColor Yellow
Write-Host ""

$copied = 0
$withStl = 0
$withoutStl = 0

foreach ($dcmFile in $selected) {
    $copied++

    # Generate unique name
    $pathParts = $dcmFile.DirectoryName.Replace($sourceRoot, "").Trim('\').Split('\')
    $caseName = $pathParts[0]  # First part is case name
    $scanType = $pathParts[-1]  # Last part is Upper/Lower/etc
    $uniqueName = "${caseName}_${scanType}_$($dcmFile.Name)"

    # Handle long names
    if ($uniqueName.Length -gt 200) {
        $hash = [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($dcmFile.FullName))).Replace("-", "").Substring(0, 8)
        $uniqueName = "${hash}_$($dcmFile.Name)"
    }

    $destDcmPath = Join-Path $destRoot $uniqueName
    $destStlPath = $destDcmPath -replace '\.dcm$', '.stl'

    # Check for STL
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

        if ($copied % 10 -eq 0 -or $copied -eq $selected.Count) {
            Write-Host "[$copied/$($selected.Count)] Pairs: $withStl, DCM-only: $withoutStl" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "ERROR: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total copied: $copied DCM files" -ForegroundColor Green
Write-Host "With STL: $withStl pairs" -ForegroundColor Green
Write-Host "Without STL: $withoutStl (need conversion)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Destination: $destRoot" -ForegroundColor Gray

$finalDcm = (Get-ChildItem -Path $destRoot -Filter "*.dcm").Count
$finalStl = (Get-ChildItem -Path $destRoot -Filter "*.stl").Count
Write-Host "Final: $finalDcm DCM, $finalStl STL" -ForegroundColor Gray

if ($withoutStl -gt 0) {
    Write-Host ""
    Write-Host "Next: .\scripts\convert-missing-stls.ps1" -ForegroundColor Yellow
}
