# Fast sample copier - finds files as it goes instead of scanning everything first
# Usage: .\copy-sample-pairs-fast.ps1 [-SampleSize 200]

param(
    [int]$SampleSize = 200
)

$sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"
$destRoot = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"

Write-Host "=== Fast DCM/STL Pair Copier ===" -ForegroundColor Cyan
Write-Host "Source: $sourceRoot" -ForegroundColor Gray
Write-Host "Destination: $destRoot" -ForegroundColor Gray
Write-Host "Target: $SampleSize files" -ForegroundColor Gray
Write-Host ""

# Create destination
if (-not (Test-Path $destRoot)) {
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
}

Write-Host "Searching for DCM files (will stop after finding $SampleSize)..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop early" -ForegroundColor Gray
Write-Host ""

$found = @()
$dirsScanned = 0
$lastUpdate = Get-Date

# Walk directories and collect DCM files until we have enough
function Find-DcmFiles {
    param($path, $maxFiles)

    try {
        $dirs = Get-ChildItem -Path $path -Directory -ErrorAction SilentlyContinue

        foreach ($dir in $dirs) {
            $script:dirsScanned++

            # Show progress every 2 seconds
            $now = Get-Date
            if (($now - $script:lastUpdate).TotalSeconds -ge 2) {
                Write-Host "`rScanned $script:dirsScanned dirs, found $($script:found.Count) DCM files..." -NoNewline -ForegroundColor Yellow
                $script:lastUpdate = $now
            }

            # Check for DCM files in current directory
            $dcmFiles = Get-ChildItem -Path $dir.FullName -Filter "*.dcm" -File -ErrorAction SilentlyContinue

            foreach ($dcm in $dcmFiles) {
                $script:found += $dcm

                if ($script:found.Count -ge $maxFiles) {
                    return $true  # Found enough
                }
            }

            # Recurse into subdirectory
            if ($script:found.Count -lt $maxFiles) {
                $done = Find-DcmFiles -path $dir.FullName -maxFiles $maxFiles
                if ($done) {
                    return $true
                }
            }
        }
    } catch {
        # Silently skip directories we can't access
    }

    return $false
}

# Start searching
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Find-DcmFiles -path $sourceRoot -maxFiles $SampleSize
$stopwatch.Stop()

Write-Host "`r" -NoNewline
Write-Host "Found $($found.Count) DCM files in $($stopwatch.Elapsed.TotalSeconds.ToString('F1'))s (scanned $dirsScanned directories)" -ForegroundColor Green
Write-Host ""

if ($found.Count -eq 0) {
    Write-Host "ERROR: No DCM files found!" -ForegroundColor Red
    exit 1
}

# Randomly select if we found more than needed
$selected = $found
if ($found.Count -gt $SampleSize) {
    Write-Host "Randomly selecting $SampleSize from $($found.Count) files..." -ForegroundColor Yellow
    $selected = $found | Get-Random -Count $SampleSize
}

Write-Host "Copying $($selected.Count) files..." -ForegroundColor Yellow
Write-Host ""

$copied = 0
$withStl = 0
$withoutStl = 0

foreach ($dcmFile in $selected) {
    $copied++

    # Generate unique name
    $parentFolder = Split-Path $dcmFile.Directory -Leaf
    $uniqueName = "${parentFolder}_$($dcmFile.Name)"

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

    # Copy DCM
    Copy-Item -Path $dcmFile.FullName -Destination $destDcmPath -Force

    # Copy STL if exists
    if ($hasStl) {
        Copy-Item -Path $sourceStlPath -Destination $destStlPath -Force
        $withStl++
        $status = "✓ (with STL)"
        $color = "Green"
    } else {
        $withoutStl++
        $status = "✓ (no STL)"
        $color = "Yellow"
    }

    if ($copied % 10 -eq 0 -or $copied -eq $selected.Count) {
        Write-Host "[$copied/$($selected.Count)] Copied $withStl pairs, $withoutStl DCM-only" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Copied: $copied DCM files" -ForegroundColor Green
Write-Host "With STL: $withStl pairs" -ForegroundColor Green
Write-Host "Without STL: $withoutStl (need conversion)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Destination: $destRoot" -ForegroundColor Gray

$finalDcm = (Get-ChildItem -Path $destRoot -Filter "*.dcm").Count
$finalStl = (Get-ChildItem -Path $destRoot -Filter "*.stl").Count
Write-Host "Files in destination: $finalDcm DCM, $finalStl STL" -ForegroundColor Gray
