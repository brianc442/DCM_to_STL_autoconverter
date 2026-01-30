# Master script: Copy samples, convert to STL, and analyze
# Usage: .\analyze-sample-batch.ps1 [-SampleSize 200] [-SkipCopy] [-SkipConvert]

param(
    [int]$SampleSize = 200,
    [switch]$SkipCopy,
    [switch]$SkipConvert
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path $PSScriptRoot -Parent
$destDir = Join-Path $projectRoot "test\dcm-stl-pairs"
$scriptsDir = $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "DCM/STL BATCH ANALYSIS PIPELINE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Project root: $projectRoot" -ForegroundColor Gray
Write-Host "Sample size: $SampleSize" -ForegroundColor Gray
Write-Host ""

# Step 1: Copy samples
if (-not $SkipCopy) {
    Write-Host "STEP 1: Copying sample files..." -ForegroundColor Yellow
    Write-Host "-----------------------------------------------------------" -ForegroundColor Gray

    # Modify the copy script to use the parameter
    $copySample = Join-Path $scriptsDir "copy-sample-pairs.ps1"
    if (-not (Test-Path $copySample)) {
        Write-Host "ERROR: copy-sample-pairs.ps1 not found!" -ForegroundColor Red
        exit 1
    }

    # Run copy script (we'll modify it inline for now)
    $sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"

    # Create destination
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    # Find and copy
    Write-Host "Scanning source directory..." -ForegroundColor Gray
    $allDcmFiles = Get-ChildItem -Path $sourceRoot -Filter "*.dcm" -Recurse -File -ErrorAction SilentlyContinue

    if ($allDcmFiles.Count -eq 0) {
        Write-Host "ERROR: No DCM files found!" -ForegroundColor Red
        exit 1
    }

    Write-Host "Found $($allDcmFiles.Count) total DCM files" -ForegroundColor Green
    $selectedCount = [Math]::Min($SampleSize, $allDcmFiles.Count)
    $selected = $allDcmFiles | Get-Random -Count $selectedCount

    Write-Host "Copying $selectedCount files..." -ForegroundColor Yellow

    $copied = 0
    $withStl = 0

    foreach ($dcmFile in $selected) {
        $copied++
        $parentFolder = Split-Path $dcmFile.Directory -Leaf
        $uniqueName = "${parentFolder}_$($dcmFile.Name)"

        if ($uniqueName.Length -gt 200) {
            $hash = [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($dcmFile.FullName))).Replace("-", "").Substring(0, 8)
            $uniqueName = "${hash}_$($dcmFile.Name)"
        }

        $destDcmPath = Join-Path $destDir $uniqueName
        $destStlPath = $destDcmPath -replace '\.dcm$', '.stl'
        $sourceStlPath = Join-Path $dcmFile.DirectoryName ($dcmFile.BaseName + ".stl")

        Copy-Item -Path $dcmFile.FullName -Destination $destDcmPath -Force

        if (Test-Path $sourceStlPath) {
            Copy-Item -Path $sourceStlPath -Destination $destStlPath -Force
            $withStl++
        }

        Write-Progress -Activity "Copying" -Status "$copied of $selectedCount" -PercentComplete (($copied / $selectedCount) * 100)
    }

    Write-Progress -Activity "Copying" -Completed

    Write-Host "✓ Copied $copied DCM files ($withStl with STL)" -ForegroundColor Green
    Write-Host ""

} else {
    Write-Host "STEP 1: Skipping copy (using existing files)" -ForegroundColor Gray
    Write-Host ""
}

# Step 2: Convert missing STLs
if (-not $SkipConvert) {
    Write-Host "STEP 2: Converting missing STL files..." -ForegroundColor Yellow
    Write-Host "-----------------------------------------------------------" -ForegroundColor Gray

    $convertScript = Join-Path $scriptsDir "convert-missing-stls.ps1"
    if (Test-Path $convertScript) {
        & $convertScript -directory $destDir
    } else {
        Write-Host "WARNING: convert-missing-stls.ps1 not found, skipping..." -ForegroundColor Yellow
    }

    Write-Host ""

} else {
    Write-Host "STEP 2: Skipping conversion" -ForegroundColor Gray
    Write-Host ""
}

# Step 3: Run batch analysis
Write-Host "STEP 3: Running batch pair analysis..." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------" -ForegroundColor Gray

$outputDir = Join-Path $projectRoot "test\analysis_results"
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$analysisOutput = Join-Path $outputDir "pair_analysis.json"
$keysDir = Join-Path $outputDir "extracted_keys"

Write-Host "Output: $analysisOutput" -ForegroundColor Gray
Write-Host "Keys: $keysDir" -ForegroundColor Gray
Write-Host ""

try {
    # Run Python batch analyzer
    python tools/batch_pair_analyzer.py $destDir --output $analysisOutput --save-keys --keys-dir $keysDir

    Write-Host ""
    Write-Host "✓ Analysis complete!" -ForegroundColor Green

} catch {
    Write-Host "ERROR running analysis: $_" -ForegroundColor Red
    exit 1
}

# Step 4: Run facet analysis
Write-Host ""
Write-Host "STEP 4: Running facet decoder analysis..." -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------" -ForegroundColor Gray

$facetOutput = Join-Path $outputDir "facet_analysis.json"

try {
    python tools/facet_decoder.py analyze $destDir --limit 1000 --output $facetOutput

    Write-Host ""
    Write-Host "✓ Facet analysis complete!" -ForegroundColor Green

} catch {
    Write-Host "ERROR running facet analysis: $_" -ForegroundColor Red
    # Don't exit, continue to summary
}

# Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "ANALYSIS COMPLETE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Results saved to:" -ForegroundColor Green
Write-Host "  Pair analysis: $analysisOutput" -ForegroundColor Gray
Write-Host "  Facet analysis: $facetOutput" -ForegroundColor Gray
Write-Host "  Extracted keys: $keysDir" -ForegroundColor Gray
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Review the analysis JSON files" -ForegroundColor Gray
Write-Host "  2. Check if SignatureHash determines the key" -ForegroundColor Gray
Write-Host "  3. Examine facet encoding patterns" -ForegroundColor Gray
Write-Host ""
