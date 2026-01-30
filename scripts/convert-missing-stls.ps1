# Convert DCM files that don't have matching STL files
# Usage: .\convert-missing-stls.ps1 [directory]

param(
    [string]$directory = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"
)

Write-Host "=== Convert Missing STL Files ===" -ForegroundColor Cyan
Write-Host "Directory: $directory" -ForegroundColor Gray
Write-Host ""

# Check if directory exists
if (-not (Test-Path $directory)) {
    Write-Host "ERROR: Directory not found: $directory" -ForegroundColor Red
    exit 1
}

# Find DCM files without matching STL
$dcmFiles = Get-ChildItem -Path $directory -Filter "*.dcm"
$missing = @()

foreach ($dcmFile in $dcmFiles) {
    $stlPath = $dcmFile.FullName -replace '\.dcm$', '.stl'
    if (-not (Test-Path $stlPath)) {
        $missing += $dcmFile
    }
}

Write-Host "Found $($dcmFiles.Count) total DCM files" -ForegroundColor Gray
Write-Host "Missing STL: $($missing.Count)" -ForegroundColor Yellow

if ($missing.Count -eq 0) {
    Write-Host "All DCM files already have matching STL files!" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "Converting DCM files to STL using SDX..." -ForegroundColor Yellow
Write-Host ""

# Load the convert-helper if available, otherwise use direct SDX calls
$convertHelper = Join-Path $PSScriptRoot "..\convert-helper.ps1"

if (Test-Path $convertHelper) {
    Write-Host "Loading convert-helper.ps1..." -ForegroundColor Gray
    . $convertHelper

    $converted = 0
    $errors = 0

    foreach ($dcmFile in $missing) {
        $converted++
        Write-Host "[$converted/$($missing.Count)] Converting: $($dcmFile.Name)" -ForegroundColor Cyan

        try {
            convert $dcmFile.FullName
            Write-Host "  ✓ Success" -ForegroundColor Green
        } catch {
            $errors++
            Write-Host "  ✗ Error: $_" -ForegroundColor Red
        }
    }

    # Cleanup
    if (Get-Command disconnect-convert -ErrorAction SilentlyContinue) {
        disconnect-convert
    }

} else {
    Write-Host "convert-helper.ps1 not found, using direct SDX conversion..." -ForegroundColor Yellow

    # Direct SDX conversion (without helper)
    $converted = 0
    $errors = 0

    foreach ($dcmFile in $missing) {
        $converted++
        $stlPath = $dcmFile.FullName -replace '\.dcm$', '.stl'

        Write-Host "[$converted/$($missing.Count)] Converting: $($dcmFile.Name)" -ForegroundColor Cyan

        try {
            # Create SDX COM object
            $sdx = New-Object -ComObject "sdx.DelcamExchange"
            $sdx.Attach()

            # Configure
            $sdx.SetOption("INPUT_FORMAT", "3Shape")
            $sdx.SetOption("OUTPUT_FORMAT", "STL")
            $sdx.SetOption("INPUT_FILE", $dcmFile.FullName)
            $sdx.SetOption("OUTPUT_FILE", $stlPath)

            # Execute
            $state = $sdx.Execute()

            if ($state -eq 0) {
                while (-not $sdx.Finished) {
                    Start-Sleep -Milliseconds 100
                }
                Write-Host "  ✓ Success" -ForegroundColor Green
            } else {
                throw "SDX returned error code: $state"
            }

            $sdx.Detach()
            [System.Runtime.Interopservices.Marshal]::ReleaseComObject($sdx) | Out-Null

        } catch {
            $errors++
            Write-Host "  ✗ Error: $_" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Attempted: $($missing.Count)" -ForegroundColor Gray
Write-Host "Successful: $($missing.Count - $errors)" -ForegroundColor Green
Write-Host "Errors: $errors" -ForegroundColor $(if ($errors -gt 0) { "Red" } else { "Green" })

# Verify final count
$finalStlCount = (Get-ChildItem -Path $directory -Filter "*.stl").Count
$finalDcmCount = (Get-ChildItem -Path $directory -Filter "*.dcm").Count

Write-Host ""
Write-Host "Final counts:" -ForegroundColor Cyan
Write-Host "  DCM: $finalDcmCount" -ForegroundColor Gray
Write-Host "  STL: $finalStlCount" -ForegroundColor Gray

if ($finalDcmCount -eq $finalStlCount) {
    Write-Host ""
    Write-Host "✓ All DCM files now have matching STL files!" -ForegroundColor Green
}
