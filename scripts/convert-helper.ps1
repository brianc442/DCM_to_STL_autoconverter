# DCM to STL Conversion Helper
# Source this script once at the start of your session: . .\convert-helper.ps1
# Usage: convert [filename or directory]
# Use -r flag for recursive search: convert -r [directory] or convert -r *
#
# SDX Error Codes:
# 0  = Success
# 1  = General error
# 2  = Invalid input file
# 3  = Invalid output file
# 4  = Conversion failed
# 5  = Unsupported format
# 6  = File not found
# 7  = SDX client is detached
# 99 = Unknown error

# Helper function to get error description
function Get-SDXErrorDescription {
    param([int]$ErrorCode)

    switch ($ErrorCode) {
        0  { return "Success" }
        1  { return "General error" }
        2  { return "Invalid input file" }
        3  { return "Invalid output file" }
        4  { return "Conversion failed" }
        5  { return "Unsupported format" }
        6  { return "File not found" }
        7  { return "SDX client is detached" }
        99 { return "Unknown error" }
        default { return "Undocumented error" }
    }
}

# Helper function to ensure SDX is attached
function Ensure-SDXAttached {
    try {
        # Try to check if the COM object is responsive
        $testFormat = $global:sdx.Option("INPUT_FORMAT")
        # If we can read the property and it's empty or not what we set, re-attach
        if ([string]::IsNullOrEmpty($testFormat) -or $testFormat -ne "3Shape") {
            throw "SDX options not configured"
        }
    }
    catch {
        try {
            # Write-Host "`n[DEBUG] Calling Attach() - Ensure-SDXAttached detected disconnection..." -ForegroundColor Magenta
            $global:sdx.Attach()
            # Write-Host "[DEBUG] Attach() completed" -ForegroundColor Magenta
            $global:sdx.Option("INPUT_FORMAT") = "3Shape"
            $global:sdx.Option("OUTPUT_FORMAT") = "STL"
        }
        catch {
            Write-Host "Warning: Failed to ensure SDX attachment: $_" -ForegroundColor Yellow
        }
    }
}

# Initialize the COM object (runs once when script is sourced)
Write-Host "Initializing sdx.DelcamExchange COM object..." -ForegroundColor Cyan
$global:sdx = New-Object -ComObject "sdx.DelcamExchange"
# Write-Host "[DEBUG] Calling Attach() - Initial setup..." -ForegroundColor Magenta
$global:sdx.Attach()
# Write-Host "[DEBUG] Attach() completed" -ForegroundColor Magenta
$global:sdx.Option("INPUT_FORMAT") = "3Shape"
$global:sdx.Option("OUTPUT_FORMAT") = "STL"
Write-Host "Ready for conversions!" -ForegroundColor Green

# Conversion function
function convert {
    param(
        [switch]$r,
        [Parameter(ValueFromRemainingArguments=$true)]
        [string[]]$Path
    )

    if (-not $Path) {
        $Path = @(Get-Location)
    }

    $filesToConvert = @()

    foreach ($p in $Path) {
        $resolvedPaths = @(Resolve-Path $p -ErrorAction SilentlyContinue)

        if (-not $resolvedPaths) {
            Write-Host "Path not found: $p" -ForegroundColor Red
            continue
        }

        # Handle each resolved path separately (Resolve-Path can return multiple paths from wildcards)
        foreach ($resolvedPath in $resolvedPaths) {
            $fullPath = $resolvedPath.ProviderPath

            if (Test-Path $fullPath -PathType Container) {
                # If it's a directory, find all .dcm files
                $params = @{
                    Path = $fullPath
                    Filter = "*.dcm"
                    File = $true
                }
                if ($r) {
                    $params['Recurse'] = $true
                }
                $filesToConvert += @(Get-ChildItem @params | Select-Object -ExpandProperty FullName)
            }
            elseif (Test-Path $fullPath -PathType Leaf) {
                # If it's a file, only add it if it's a .dcm file
                if ($fullPath -like "*.dcm") {
                    $filesToConvert += $fullPath
                }
            }
        }
    }

    if ($filesToConvert.Count -eq 0) {
        Write-Host "No .dcm files found." -ForegroundColor Yellow
        return
    }

    Write-Host "Converting $($filesToConvert.Count) file(s)..." -ForegroundColor Cyan

    foreach ($file in $filesToConvert) {
        $outputFile = [System.IO.Path]::ChangeExtension($file, ".stl")

        Write-Host "Converting: $(Split-Path $file -Leaf)" -ForegroundColor Gray -NoNewline

        $global:sdx.Option("INPUT_FILE") = $file
        $global:sdx.Option("OUTPUT_FILE") = $outputFile

        $result = $global:sdx.Execute()

        # If we get Error 7 (client detached), re-attach and retry once
        if ($result -eq 7) {
            # Write-Host ""
            # Write-Host "[DEBUG] Error 7 detected - Calling Attach()..." -ForegroundColor Magenta
            try {
                $global:sdx.Attach()
                # Write-Host "[DEBUG] Attach() completed - Retrying conversion" -ForegroundColor Magenta
                $global:sdx.Option("INPUT_FORMAT") = "3Shape"
                $global:sdx.Option("OUTPUT_FORMAT") = "STL"
                $global:sdx.Option("INPUT_FILE") = $file
                $global:sdx.Option("OUTPUT_FILE") = $outputFile
                Write-Host " (retrying)" -ForegroundColor Yellow -NoNewline
                $result = $global:sdx.Execute()
            }
            catch {
                Write-Host " ✗ Failed to re-attach: $_" -ForegroundColor Red
                continue
            }
        }

        if ($result -eq 0) {
            # CRITICAL: Wait for the conversion to actually finish before moving to the next file
            # This prevents the SDX client from detaching between conversions
            $waitCount = 0
            while (-not $global:sdx.Finished) {
                Start-Sleep -Milliseconds 25
                $waitCount++
                if ($waitCount -gt 1200) {  # 30 second timeout (1200 * 25ms)
                    Write-Host " ✗ Timeout waiting for conversion to finish" -ForegroundColor Red
                    break
                }
            }
            # Check for output file immediately first (fast path for local drives)
            if (Test-Path $outputFile) {
                Write-Host " ✓" -ForegroundColor Green
            }
            else {
                # If not found immediately, add delays for network share synchronization
                $fileExists = $false
                for ($i = 0; $i -lt 5; $i++) {
                    Start-Sleep -Milliseconds 200
                    if (Test-Path $outputFile) {
                        $fileExists = $true
                        Write-Host " ✓" -ForegroundColor Green
                        break
                    }
                }
                if (-not $fileExists) {
                    Write-Host " ✓ (succeeded but file not found at: $outputFile)" -ForegroundColor Yellow
                }
            }
        }
        else {
            $errorDesc = Get-SDXErrorDescription -ErrorCode $result
            Write-Host " ✗ (Error $result`: $errorDesc)" -ForegroundColor Red
        }
    }

    Write-Host "Conversions complete!" -ForegroundColor Green
}

# Cleanup function
function disconnect-convert {
    Write-Host "Detaching sdx COM object..." -ForegroundColor Yellow
    $global:sdx.Detach()
    Remove-Variable -Name sdx -Scope Global
    Write-Host "Done." -ForegroundColor Green
}
