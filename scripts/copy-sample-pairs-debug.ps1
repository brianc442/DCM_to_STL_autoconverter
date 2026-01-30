# Debug version with verbose output
param(
    [int]$SampleSize = 200
)

$sourceRoot = "\\CDIMANQ30\Creoman-Active\CADCAM\3Shape Dental System Orders"
$destRoot = "C:\Users\bconn\PycharmProjects\DCM to STL autoconverter\test\dcm-stl-pairs"

Write-Host "=== Debug Sample Copier ===" -ForegroundColor Cyan
Write-Host ""

# Test 1: Can we access the network share?
Write-Host "Test 1: Network share access..." -ForegroundColor Yellow
if (Test-Path $sourceRoot) {
    Write-Host "  ✓ Can access $sourceRoot" -ForegroundColor Green
} else {
    Write-Host "  ✗ Cannot access $sourceRoot" -ForegroundColor Red
    exit 1
}

# Test 2: Can we list top-level directories?
Write-Host ""
Write-Host "Test 2: Listing first 5 case folders..." -ForegroundColor Yellow
try {
    $topDirs = Get-ChildItem -Path $sourceRoot -Directory -ErrorAction Stop | Select-Object -First 5
    Write-Host "  Found $($topDirs.Count) sample directories:" -ForegroundColor Green
    foreach ($dir in $topDirs) {
        Write-Host "    - $($dir.Name)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  ✗ Error: $_" -ForegroundColor Red
}

# Test 3: Check a specific case folder structure
Write-Host ""
Write-Host "Test 3: Checking first case folder structure..." -ForegroundColor Yellow
$firstCase = Get-ChildItem -Path $sourceRoot -Directory | Select-Object -First 1
if ($firstCase) {
    Write-Host "  Case: $($firstCase.Name)" -ForegroundColor Gray

    $scansFolder = Join-Path $firstCase.FullName "Scans"
    if (Test-Path $scansFolder) {
        Write-Host "  ✓ Has Scans folder" -ForegroundColor Green

        $scanSubdirs = Get-ChildItem -Path $scansFolder -Directory
        Write-Host "    Subdirs: $($scanSubdirs.Name -join ', ')" -ForegroundColor Gray

        # Look for DCM files
        foreach ($subdir in $scanSubdirs) {
            $dcms = Get-ChildItem -Path $subdir.FullName -Filter "*.dcm" -File
            Write-Host "    $($subdir.Name): $($dcms.Count) DCM files" -ForegroundColor Gray
            if ($dcms.Count -gt 0) {
                Write-Host "      Example: $($dcms[0].Name)" -ForegroundColor DarkGray
            }
        }
    } else {
        Write-Host "  ✗ No Scans folder" -ForegroundColor Red
    }
}

# Test 4: Try Get-ChildItem with different approaches
Write-Host ""
Write-Host "Test 4: Testing Get-ChildItem approaches..." -ForegroundColor Yellow

Write-Host "  Approach A: -Recurse -Depth 3 (10 second timeout)..." -ForegroundColor Gray
$job = Start-Job -ScriptBlock {
    param($path)
    Get-ChildItem -Path $path -Filter "*.dcm" -Recurse -Depth 3 -File -ErrorAction SilentlyContinue |
        Where-Object { $_.DirectoryName -like "*\Scans\*" } |
        Select-Object -First 10
} -ArgumentList $sourceRoot

$timeout = Wait-Job $job -Timeout 10
if ($timeout) {
    $results = Receive-Job $job
    Write-Host "    Found $($results.Count) files in 10s" -ForegroundColor Green
    $results | ForEach-Object { Write-Host "      - $($_.Name)" -ForegroundColor DarkGray }
} else {
    Write-Host "    Timed out (still searching after 10s)" -ForegroundColor Yellow
}
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Test 5: Manual walk (first 10 case folders)..." -ForegroundColor Yellow
$caseFolders = Get-ChildItem -Path $sourceRoot -Directory | Select-Object -First 10
$foundFiles = @()

foreach ($case in $caseFolders) {
    $scansPath = Join-Path $case.FullName "Scans"
    if (Test-Path $scansPath) {
        $subdirs = Get-ChildItem -Path $scansPath -Directory -ErrorAction SilentlyContinue
        foreach ($subdir in $subdirs) {
            $dcms = Get-ChildItem -Path $subdir.FullName -Filter "*.dcm" -File -ErrorAction SilentlyContinue
            $foundFiles += $dcms

            if ($foundFiles.Count -ge 10) { break }
        }
    }
    if ($foundFiles.Count -ge 10) { break }
}

Write-Host "  Manual walk found $($foundFiles.Count) files from first 10 cases" -ForegroundColor Green
$foundFiles | Select-Object -First 5 | ForEach-Object { Write-Host "    - $($_.Name)" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "=== Diagnosis ===" -ForegroundColor Cyan
Write-Host "Based on these tests, we can determine the best approach." -ForegroundColor Gray
