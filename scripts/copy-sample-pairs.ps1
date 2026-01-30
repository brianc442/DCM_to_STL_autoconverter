# Copy 200 random DCM/STL pairs from network share
# Usage: .\copy-sample-pairs.ps1

$sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"
$destRoot = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"
$sampleSize = 200

Write-Host "=== DCM/STL Pair Sample Copier ===" -ForegroundColor Cyan
Write-Host "Source: $sourceRoot" -ForegroundColor Gray
Write-Host "Destination: $destRoot" -ForegroundColor Gray
Write-Host "Sample size: $sampleSize pairs" -ForegroundColor Gray
Write-Host ""

# Create destination directory
if (-not (Test-Path $destRoot)) {
    Write-Host "Creating destination directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
}

# Find all DCM files recursively
Write-Host "Scanning for DCM files..." -ForegroundColor Yellow
$allDcmFiles = Get-ChildItem -Path $sourceRoot -Filter "*.dcm" -Recurse -File -ErrorAction SilentlyContinue

Write-Host "Found $($allDcmFiles.Count) total DCM files" -ForegroundColor Green

if ($allDcmFiles.Count -eq 0) {
    Write-Host "ERROR: No DCM files found in source directory!" -ForegroundColor Red
    exit 1
}

# Randomly select sample
$sampleCount = [Math]::Min($sampleSize, $allDcmFiles.Count)
Write-Host "Randomly selecting $sampleCount files..." -ForegroundColor Yellow
$selectedDcmFiles = $allDcmFiles | Get-Random -Count $sampleCount

# Copy files with progress
$copied = 0
$withStl = 0
$withoutStl = 0
$errors = 0

Write-Host ""
Write-Host "Copying files..." -ForegroundColor Yellow

foreach ($dcmFile in $selectedDcmFiles) {
    $copied++
    $percentComplete = [int](($copied / $sampleCount) * 100)

    # Generate unique filename (use parent folder + filename to avoid conflicts)
    $parentFolder = Split-Path $dcmFile.Directory -Leaf
    $uniqueName = "${parentFolder}_$($dcmFile.Name)"

    # Handle very long names
    if ($uniqueName.Length -gt 200) {
        $hash = [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($dcmFile.FullName))).Replace("-", "").Substring(0, 8)
        $uniqueName = "${hash}_$($dcmFile.Name)"
    }

    $destDcmPath = Join-Path $destRoot $uniqueName
    $destStlPath = $destDcmPath -replace '\.dcm$', '.stl'

    # Check for corresponding STL
    $sourceDirPath = $dcmFile.DirectoryName
    $stlFileName = $dcmFile.BaseName + ".stl"
    $sourceStlPath = Join-Path $sourceDirPath $stlFileName
    $hasStl = Test-Path $sourceStlPath

    try {
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

        Write-Progress -Activity "Copying files" -Status "$copied of $sampleCount" -PercentComplete $percentComplete
        Write-Host "[$copied/$sampleCount] $uniqueName - $status" -ForegroundColor $color

    } catch {
        $errors++
        Write-Host "[$copied/$sampleCount] $uniqueName - ERROR: $_" -ForegroundColor Red
    }
}

Write-Progress -Activity "Copying files" -Completed

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total copied: $copied DCM files" -ForegroundColor Green
Write-Host "With STL: $withStl pairs" -ForegroundColor Green
Write-Host "Without STL: $withoutStl (DCM only)" -ForegroundColor Yellow
Write-Host "Errors: $errors" -ForegroundColor $(if ($errors -gt 0) { "Red" } else { "Green" })
Write-Host "Destination: $destRoot" -ForegroundColor Gray

# Show file count in destination
$finalDcmCount = (Get-ChildItem -Path $destRoot -Filter "*.dcm").Count
$finalStlCount = (Get-ChildItem -Path $destRoot -Filter "*.stl").Count
Write-Host ""
Write-Host "Files in destination:" -ForegroundColor Cyan
Write-Host "  DCM: $finalDcmCount" -ForegroundColor Gray
Write-Host "  STL: $finalStlCount" -ForegroundColor Gray

if ($withoutStl -gt 0) {
    Write-Host ""
    Write-Host "NOTE: $withoutStl files don't have matching STL files." -ForegroundColor Yellow
    Write-Host "You'll need to convert these with SDX first." -ForegroundColor Yellow
}
