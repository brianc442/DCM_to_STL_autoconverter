# Sample copier optimized for 3Shape folder structure
# Structure: [Root]\[Case]\Scan\[Upper|Lower|Misc]\*.dcm
# Usage: .\copy-sample-pairs-v2.ps1 [-SampleSize 200]

param(
    [int]$SampleSize = 200
)

$sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"
$destRoot = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"

Write-Host "=== 3Shape Sample Copier v2 ===" -ForegroundColor Cyan
Write-Host "Source: $sourceRoot" -ForegroundColor Gray
Write-Host "Destination: $destRoot" -ForegroundColor Gray
Write-Host "Target: $SampleSize files" -ForegroundColor Gray
Write-Host ""
Write-Host "Expected structure: [Case]\Scan\[Upper|Lower|Misc]\*.dcm" -ForegroundColor Gray
Write-Host ""

# Create destination
if (-not (Test-Path $destRoot)) {
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
}

Write-Host "Scanning case folders..." -ForegroundColor Yellow
Write-Host ""

$dcmFiles = @()
$caseFoldersScanned = 0
$lastUpdate = Get-Date

# Get top-level case folders
$caseFolders = Get-ChildItem -Path $sourceRoot -Directory -ErrorAction SilentlyContinue

Write-Host "Found $($caseFolders.Count) case folders" -ForegroundColor Green
Write-Host "Collecting DCM files..." -ForegroundColor Yellow
Write-Host ""

foreach ($caseFolder in $caseFolders) {
    $caseFoldersScanned++

    # Show progress every 2 seconds
    $now = Get-Date
    if (($now - $lastUpdate).TotalSeconds -ge 2) {
        Write-Host "`rScanned $caseFoldersScanned/$($caseFolders.Count) cases, found $($dcmFiles.Count) DCM files..." -NoNewline -ForegroundColor Yellow
        $lastUpdate = $now
    }

    # Look for Scan folder
    $scanFolder = Join-Path $caseFolder.FullName "Scan"

    if (Test-Path $scanFolder) {
        # Look in Upper, Lower, Misc subfolders
        $scanSubfolders = Get-ChildItem -Path $scanFolder -Directory -ErrorAction SilentlyContinue

        foreach ($subfolder in $scanSubfolders) {
            # Get all DCM files in this subfolder
            $dcms = Get-ChildItem -Path $subfolder.FullName -Filter "*.dcm" -File -ErrorAction SilentlyContinue

            foreach ($dcm in $dcms) {
                $dcmFiles += $dcm

                # Stop if we have enough
                if ($dcmFiles.Count -ge $SampleSize) {
                    Write-Host "`r" -NoNewline
                    Write-Host "Found $($dcmFiles.Count) DCM files!" -ForegroundColor Green
                    break
                }
            }

            if ($dcmFiles.Count -ge $SampleSize) { break }
        }
    }

    if ($dcmFiles.Count -ge $SampleSize) { break }
}

Write-Host "`r" -NoNewline
Write-Host "Scanned $caseFoldersScanned cases, found $($dcmFiles.Count) DCM files" -ForegroundColor Green
Write-Host ""

if ($dcmFiles.Count -eq 0) {
    Write-Host "ERROR: No DCM files found!" -ForegroundColor Red
    Write-Host "Please verify the folder structure and permissions." -ForegroundColor Yellow
    exit 1
}

# Take exactly what we need
$selected = $dcmFiles
if ($dcmFiles.Count -gt $SampleSize) {
    Write-Host "Randomly selecting $SampleSize from $($dcmFiles.Count) files..." -ForegroundColor Yellow
    $selected = $dcmFiles | Get-Random -Count $SampleSize
}

Write-Host "Copying $($selected.Count) files..." -ForegroundColor Yellow
Write-Host ""

$copied = 0
$withStl = 0
$withoutStl = 0

foreach ($dcmFile in $selected) {
    $copied++

    # Generate unique name using case folder
    $caseName = Split-Path (Split-Path (Split-Path $dcmFile.Directory -Parent) -Parent) -Leaf
    $scanType = Split-Path $dcmFile.Directory -Leaf  # Upper/Lower/Misc
    $uniqueName = "${caseName}_${scanType}_$($dcmFile.Name)"

    # Handle long names
    if ($uniqueName.Length -gt 200) {
        $hash = [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($dcmFile.FullName))).Replace("-", "").Substring(0, 8)
        $uniqueName = "${hash}_$($dcmFile.Name)"
    }

    $destDcmPath = Join-Path $destRoot $uniqueName
    $destStlPath = $destDcmPath -replace '\.dcm$', '.stl'

    # Check for STL in same directory
    $sourceStlPath = Join-Path $dcmFile.DirectoryName ($dcmFile.BaseName + ".stl")
    $hasStl = Test-Path $sourceStlPath

    try {
        # Copy DCM
        Copy-Item -Path $dcmFile.FullName -Destination $destDcmPath -Force

        # Copy STL if exists
        if ($hasStl) {
            Copy-Item -Path $sourceStlPath -Destination $destStlPath -Force
            $withStl++
        } else {
            $withoutStl++
        }

        # Progress update every 10 files
        if ($copied % 10 -eq 0 -or $copied -eq $selected.Count) {
            Write-Host "[$copied/$($selected.Count)] Pairs: $withStl, DCM-only: $withoutStl" -ForegroundColor Cyan
        }
    } catch {
        Write-Host "ERROR copying $($dcmFile.Name): $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Copied: $copied DCM files" -ForegroundColor Green
Write-Host "With STL: $withStl complete pairs" -ForegroundColor Green
Write-Host "Without STL: $withoutStl (need conversion)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Destination: $destRoot" -ForegroundColor Gray

$finalDcm = (Get-ChildItem -Path $destRoot -Filter "*.dcm").Count
$finalStl = (Get-ChildItem -Path $destRoot -Filter "*.stl").Count
Write-Host "Final count: $finalDcm DCM, $finalStl STL" -ForegroundColor Gray

if ($withoutStl -gt 0) {
    Write-Host ""
    Write-Host "Next step: Run .\scripts\convert-missing-stls.ps1 to convert DCM files without STL" -ForegroundColor Yellow
}
