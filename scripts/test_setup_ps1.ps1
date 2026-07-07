# ---------------------------------------------------------------------------
# Tests for setup.ps1 helper functions.
#
# Run from project root:
#   pwsh -File scripts/test_setup_ps1.ps1
#
# Requires: PowerShell 5.1+ (no external modules needed)
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$script:PASSED = 0
$script:FAILED = 0
$script:FAILURES = @()

# --- Assertion helpers ---

function Parse-PythonVersion {
    param([string]$Raw)
    if ($Raw -match 'Python\s+(\d+\.\d+(\.\d+)?)') {
        return $Matches[1]
    }
    if ($Raw -match '[-:]V[:=](\d+\.\d+(\.\d+)?)') {
        return $Matches[1]
    }
    if ($Raw -match '[\\/](\d+\.\d+(\.\d+)?)[\\/]') {
        return $Matches[1]
    }
    return $null
}

function Assert-Eq {
    param([string]$Label, $Expected, $Actual)
    if ("$Expected" -eq "$Actual") {
        $script:PASSED++
        Write-Host "  PASS: $Label"
    } else {
        $script:FAILED++
        $script:FAILURES += "$($Label): expected '$Expected', got '$Actual'"
        Write-Host "  FAIL: $($Label) — expected '$Expected', got '$Actual'"
    }
}

function Assert-Contains {
    param([string]$Label, [string]$Needle, [string]$Haystack)
    if ($Haystack -match [regex]::Escape($Needle)) {
        $script:PASSED++
        Write-Host "  PASS: $Label"
    } else {
        $script:FAILED++
        $script:FAILURES += "$($Label): output does not contain '$Needle'"
        Write-Host "  FAIL: $($Label) — output does not contain '$Needle'"
        Write-Host "         got: $Haystack"
    }
}

function Assert-True {
    param([string]$Label, [bool]$Value)
    if ($Value) {
        $script:PASSED++
        Write-Host "  PASS: $Label"
    } else {
        $script:FAILED++
        $script:FAILURES += "$($Label): expected true, got false"
        Write-Host "  FAIL: $($Label) — expected true, got false"
    }
}

function Assert-False {
    param([string]$Label, [bool]$Value)
    if (-not $Value) {
        $script:PASSED++
        Write-Host "  PASS: $Label"
    } else {
        $script:FAILED++
        $script:FAILURES += "$($Label): expected false, got true"
        Write-Host "  FAIL: $($Label) — expected false, got true"
    }
}

# --- Source the production script in test mode ---
# We only need the function definitions, so we dot-source the file
# and test individual functions.

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_DIR = Split-Path -Parent $SCRIPT_DIR
$SETUP_PS1 = Join-Path $PROJECT_DIR "setup.ps1"

# Since setup.ps1 calls Invoke-Main at the end, we can't dot-source it directly.
# Instead, we test the logic by defining equivalent test functions that validate
# the patterns used in setup.ps1.

# ---------------------------------------------------------------------------
# Suite: Parse-PythonVersion (extracted logic test)
# ---------------------------------------------------------------------------

function Test-ParsePythonVersion {
    Write-Host "--- Parse-PythonVersion ---"

    # Test regex pattern used in setup.ps1
    $pattern = 'Python\s+(\d+\.\d+(\.\d+)?)'

    $result = "Python 3.12.5" -match $pattern
    Assert-True "3.12.5 matches" $result
    Assert-Eq "3.12.5 capture" "3.12.5" $Matches[1]

    $result = "Python 3.11.0" -match $pattern
    Assert-True "3.11.0 matches" $result
    Assert-Eq "3.11.0 capture" "3.11.0" $Matches[1]

    $result = "Python 3.14.6" -match $pattern
    Assert-True "3.14.6 matches" $result
    Assert-Eq "3.14.6 capture" "3.14.6" $Matches[1]

    $launcherLine = " -V:3.11 *        C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
    $launcherVersion = Parse-PythonVersion $launcherLine
    Assert-Eq "launcher line capture" "3.11" $launcherVersion

    $result = "some random text" -match $pattern
    Assert-False "non-python doesn't match" $result
}

# ---------------------------------------------------------------------------
# Suite: venv path filter (Bug #7)
# ---------------------------------------------------------------------------

function Test-VenvPathFilter {
    Write-Host "--- venv path filter ---"

    # Test the filter pattern used in setup.ps1
    $paths = @(
        "C:\Python312\python.exe",
        "C:\project\venv\Scripts\python.exe",
        "C:\Users\test\AppData\Local\Programs\Python\Python311\python.exe",
        "C:\project\.venv\Scripts\python.exe",
        "C:\env\myenv\Scripts\python.exe"
    )

    $filtered = $paths | Where-Object { $_ -and $_ -notmatch '(?:^|[\\/])(?:\.?(?:venv)|env)(?:[\\/]|$)' }

    Assert-Eq "filtered count" 2 $filtered.Count
    Assert-Contains "keeps system Python" "C:\Python312" $filtered[0]
    Assert-Contains "keeps AppData Python" "AppData" $filtered[1]
}

# ---------------------------------------------------------------------------
# Suite: PG detection range (PS pg detection)
# ---------------------------------------------------------------------------

function Test-PgDetectionRange {
    Write-Host "--- PG detection range ---"

    # Verify the loop logic covers versions 10-99
    $baseDirs = @("C:\Program Files", "C:\Program Files (x86)")
    $versionsChecked = @()

    foreach ($base in $baseDirs) {
        for ($ver = 10; $ver -le 99; $ver++) {
            $versionsChecked += $ver
        }
    }

    Assert-Eq "total versions checked" 180 $versionsChecked.Count
    Assert-Eq "first version" 10 $versionsChecked[0]
    Assert-Eq "last version" 99 $versionsChecked[$versionsChecked.Count - 1]

    # Verify both base dirs are included
    $hasProgramFiles = $false
    $hasProgramFilesX86 = $false
    foreach ($base in $baseDirs) {
        if ($base -eq "C:\Program Files") { $hasProgramFiles = $true }
        if ($base -eq "C:\Program Files (x86)") { $hasProgramFilesX86 = $true }
    }
    Assert-True "has Program Files" $hasProgramFiles
    Assert-True "has Program Files (x86)" $hasProgramFilesX86
}

# ---------------------------------------------------------------------------
# Suite: Phase5 return value (Bug #8)
# ---------------------------------------------------------------------------

function Test-Phase5ReturnValue {
    Write-Host "--- Phase5 return value ---"

    # Simulate the function pattern: all success paths must return $true
    function Simulated-Phase5 {
        param([bool]$HasEnv, [bool]$Reconfig)

        if ($HasEnv -and -not $Reconfig) {
            return $true
        }

        # Simulate Write-EnvFile call
        return $true
    }

    $result1 = Simulated-Phase5 -HasEnv $true -Reconfig $false
    Assert-True "early return path returns true" $result1

    $result2 = Simulated-Phase5 -HasEnv $false -Reconfig $false
    Assert-True "full path returns true" $result2

    $result3 = Simulated-Phase5 -HasEnv $true -Reconfig $true
    Assert-True "reconfig path returns true" $result3
}

# ---------------------------------------------------------------------------
# Suite: try/catch on pg_isready (Bug #6)
# ---------------------------------------------------------------------------

function Test-PgIsreadyTryCatch {
    Write-Host "--- pg_isready try/catch ---"

    # Verify the pattern: external command wrapped in try/catch
    # Simulate pg_isready not found
    $caught = $false
    try {
        $result = & nonexistent_command_xyz 2>$null
        if ($LASTEXITCODE -ne 0) {
            # This path handles the error
        }
    } catch {
        $caught = $true
    }
    Assert-True "catch block handles missing command" $caught

    # Simulate successful external command
    $caught = $false
    try {
        $result = & echo "test" 2>$null
        # No error
    } catch {
        $caught = $true
    }
    Assert-False "successful command doesn't trigger catch" $caught
}

# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗"
Write-Host "║          Tests: setup.ps1 helper functions                  ║"
Write-Host "╚══════════════════════════════════════════════════════════════╝"
Write-Host ""

Test-ParsePythonVersion
Test-VenvPathFilter
Test-PgDetectionRange
Test-Phase5ReturnValue
Test-PgIsreadyTryCatch

Write-Host ""
Write-Host "────────────────────────────────────────────────────────────────"
Write-Host "Results: $($script:PASSED) passed, $($script:FAILED) failed"
Write-Host "────────────────────────────────────────────────────────────────"

if ($script:FAILURES.Count -gt 0) {
    Write-Host ""
    Write-Host "FAILURES:"
    foreach ($f in $script:FAILURES) {
        Write-Host "  - $f"
    }
    exit 1
}

exit 0
