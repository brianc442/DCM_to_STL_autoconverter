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
    Write-Host "Scanning (finding $SampleSize files)..." -ForegroundColor Yellow

    # Collect file paths only (fast - no copying yet)
    Get-ChildItem -Path $sourceRoot -Filter "*.dcm" -Recurse -Depth 3 -File -ErrorAction SilentlyContinue |
        Where-Object { $_.DirectoryName -like "*\Scans\*" } |
        ForEach-Object {
            $dcmFiles += $_
            $filesFound++

            # Show progress
            if ($filesFound % 50 -eq 0) {
                $elapsed = $stopwatch.Elapsed.TotalSeconds
                $rate = $filesFound / $elapsed
                Write-Host "`rFound $filesFound files ($($rate.ToString('F1'))/sec)..." -NoNewline -ForegroundColor Yellow
            }

            # Stop once we have enough
            if ($filesFound -ge $SampleSize) {
                Write-Host "`r" -NoNewline
                break
            }
        }
} catch {
    Write-Host "`nWarning: Search interrupted" -ForegroundColor Yellow
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

Write-Host "Copying $($selected.Count) files (using parallel jobs for speed)..." -ForegroundColor Yellow
Write-Host ""

$copyStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

# Check PowerShell version for parallel support
$psVersion = $PSVersionTable.PSVersion.Major

if ($psVersion -ge 7) {
    # Use parallel copying (PowerShell 7+)
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
    # Fallback to sequential copy (PowerShell 5.x)
    Write-Host "Using sequential copy (upgrade to PowerShell 7 for faster parallel copy)..." -ForegroundColor Gray

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

            if ($copied % 10 -eq 0) {
                Write-Host "`r[$copied/$($selected.Count)] Pairs: $withStl, DCM-only: $withoutStl" -NoNewline -ForegroundColor Cyan
            }
        } catch {
            Write-Host "`nERROR: $_" -ForegroundColor Red
        }
    }
    Write-Host ""
}

$copyStopwatch.Stop()
Write-Host "Copied in $($copyStopwatch.Elapsed.TotalSeconds.ToString('F1'))s" -ForegroundColor Green

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
