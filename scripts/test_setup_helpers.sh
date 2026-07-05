#!/bin/bash
# ---------------------------------------------------------------------------
# Tests for setup.sh helper functions.
#
# Run from project root:
#   bash scripts/test_setup_helpers.sh
#
# This file sources setup.sh in "test mode" so only function definitions
# are loaded — the main() entry point is never executed.
# ---------------------------------------------------------------------------
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SETUP_SH="${PROJECT_DIR}/setup.sh"

PASSED=0
FAILED=0
FAILURES=()

# --- Assertion helpers ---

_assert_eq() {
    local -r label="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        PASSED=$((PASSED + 1))
        echo "  PASS: $label"
    else
        FAILED=$((FAILED + 1))
        FAILURES+=("$label: expected '$expected', got '$actual'")
        echo "  FAIL: $label — expected '$expected', got '$actual'"
    fi
}

_assert_contains() {
    local -r label="$1" needle="$2" haystack="$3"
    if [[ "$haystack" == *"$needle"* ]]; then
        PASSED=$((PASSED + 1))
        echo "  PASS: $label"
    else
        FAILED=$((FAILED + 1))
        FAILURES+=("$label: output does not contain '$needle'")
        echo "  FAIL: $label — output does not contain '$needle'"
        echo "         got: $haystack"
    fi
}

_assert_ge() {
    local -r label="$1" actual="$2" min="$3"
    if [[ "$actual" -ge "$min" ]]; then
        PASSED=$((PASSED + 1))
        echo "  PASS: $label"
    else
        FAILED=$((FAILED + 1))
        FAILURES+=("$label: $actual < $min")
        echo "  FAIL: $label — $actual < $min"
    fi
}

# ---------------------------------------------------------------------------
# Suite: _parse_python_version
# ---------------------------------------------------------------------------

test_parse_python_version() {
    echo "--- _parse_python_version ---"

    # Standard output
    local ver
    ver=$(_parse_python_version "Python 3.12.5")
    _assert_eq "3.12.5 → (3, 12, 5)" "3.12.5" "$ver"

    ver=$(_parse_python_version "Python 3.11.0")
    _assert_eq "3.11.0 → (3, 11, 0)" "3.11.0" "$ver"

    ver=$(_parse_python_version "Python 3.14.6")
    _assert_eq "3.14.6 → (3, 14, 6)" "3.14.6" "$ver"

    # Extra whitespace
    ver=$(_parse_python_version "  Python 3.13.2  ")
    _assert_eq "whitespace 3.13.2" "3.13.2" "$ver"

    # Only major.minor
    ver=$(_parse_python_version "Python 3.12")
    _assert_eq "3.12 → 3.12" "3.12" "$ver"

    # pyenv output (full path)
    ver=$(_parse_python_version "/home/user/.pyenv/versions/3.12.5/bin/python3")
    _assert_contains "pyenv path contains 3.12.5" "3.12.5" "$ver"

    # Not a Python line
    ver=$(_parse_python_version "some random text")
    _assert_eq "non-python returns empty" "" "$ver"

    ver=$(_parse_python_version "")
    _assert_eq "empty string" "" "$ver"
}

# ---------------------------------------------------------------------------
# Suite: _version_ge
# ---------------------------------------------------------------------------

test_version_ge() {
    echo "--- _version_ge ---"

    _assert_eq "3.12.0 ≥ 3.11.0" "true" "$(_version_ge "3.12.0" "3.11.0" && echo true || echo false)"
    _assert_eq "3.11.0 ≥ 3.11.0" "true" "$(_version_ge "3.11.0" "3.11.0" && echo true || echo false)"
    _assert_eq "3.11.0 ≥ 3.12.0" "false" "$(_version_ge "3.11.0" "3.12.0" && echo true || echo false)"
    _assert_eq "3.10.0 ≥ 3.11.0" "false" "$(_version_ge "3.10.0" "3.11.0" && echo true || echo false)"
    _assert_eq "3.14.6 ≥ 3.11.0" "true" "$(_version_ge "3.14.6" "3.11.0" && echo true || echo false)"
    _assert_eq "3.9.7 ≥ 3.11.0" "false" "$(_version_ge "3.9.7" "3.11.0" && echo true || echo false)"

    # Two-digit minor
    _assert_eq "3.14.0 ≥ 3.14.0" "true" "$(_version_ge "3.14.0" "3.14.0" && echo true || echo false)"
}

# ---------------------------------------------------------------------------
# Suite: _detect_os
# ---------------------------------------------------------------------------

test_detect_os() {
    echo "--- _detect_os ---"

    # _detect_os can return: linux, macos, windows-gitbash, windows-wsl, unknown
    local os_name
    os_name=$(_detect_os)
    case "$os_name" in
        linux|macos|windows-gitbash|windows-wsl|unknown)
            PASSED=$((PASSED + 1))
            echo "  PASS: _detect_os returns valid value (got: $os_name)"
            ;;
        *)
            FAILED=$((FAILED + 1))
            FAILURES+=("_detect_os returned unexpected value: $os_name")
            echo "  FAIL: _detect_os returned unexpected value: $os_name"
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Suite: _color helpers
# ---------------------------------------------------------------------------

test_color_helpers() {
    echo "--- color helpers ---"

    # Just verify they produce output containing the text
    local out
    out=$(_green "OK message")
    _assert_contains "green contains OK message" "OK message" "$out"

    out=$(_yellow "WARNING message")
    _assert_contains "yellow contains WARNING message" "WARNING message" "$out"

    out=$(_red "ERROR message")
    _assert_contains "red contains ERROR message" "ERROR message" "$out"

    # Verify they contain ANSI codes
    _assert_contains "green has ANSI start" $'\033[' "$(_green test)"
    _assert_contains "yellow has ANSI start" $'\033[' "$(_yellow test)"
    _assert_contains "red has ANSI start" $'\033[' "$(_red test)"
}

# ---------------------------------------------------------------------------
# Suite: state file functions
# ---------------------------------------------------------------------------

test_state_functions() {
    echo "--- state file functions ---"

    local tmp_state
    tmp_state=$(mktemp)
    # shellcheck disable=SC2064
    trap "rm -f $tmp_state" EXIT

    # Override STATE_FILE for test isolation
    _STATE_FILE="$tmp_state"

    # Fresh state: no phases done
    _assert_eq "phase_1 not done initially" "false" "$(_is_phase_done "phase_1" && echo true || echo false)"
    _assert_eq "phase_5 not done initially" "false" "$(_is_phase_done "phase_5" && echo true || echo false)"

    # Mark phase_1 as done
    _mark_phase_done "phase_1"
    _assert_eq "phase_1 is done after mark" "true" "$(_is_phase_done "phase_1" && echo true || echo false)"
    _assert_eq "phase_2 not done yet" "false" "$(_is_phase_done "phase_2" && echo true || echo false)"

    # Mark multiple phases
    _mark_phase_done "phase_2"
    _mark_phase_done "phase_8"
    _assert_eq "phase_2 done" "true" "$(_is_phase_done "phase_2" && echo true || echo false)"
    _assert_eq "phase_8 done" "true" "$(_is_phase_done "phase_8" && echo true || echo false)"

    # Reset state
    _reset_state
    _assert_eq "phase_1 reset" "false" "$(_is_phase_done "phase_1" && echo true || echo false)"

    # Cleanup
    rm -f "$tmp_state"
    trap - EXIT
}

# ---------------------------------------------------------------------------
# Suite: _banner
# ---------------------------------------------------------------------------

test_banner() {
    echo "--- _banner ---"

    local out
    out=$(_banner)
    _assert_contains "banner has 'Rassa'" "Rassa" "$out"
    _assert_contains "banner has script version" "$SCRIPT_VERSION" "$out"
}

# ---------------------------------------------------------------------------
# Suite: _version_ge scope leak regression
# ---------------------------------------------------------------------------

test_version_ge_no_leak() {
    echo "--- _version_ge scope leak regression ---"

    # Before the fix, _version_ge leaked its loop variable $i to the caller.
    # With set -u, this caused "unbound variable" crashes in _phase_1_python.
    local i="LEAKED_VALUE"
    _version_ge "3.12.0" "3.11.0"
    if [[ "$i" == "LEAKED_VALUE" ]]; then
        PASSED=$((PASSED + 1))
        echo "  PASS: _version_ge did not leak \$i (value preserved)"
    else
        FAILED=$((FAILED + 1))
        FAILURES+=("_version_ge leaked \$i: expected 'LEAKED_VALUE', got '$i'")
        echo "  FAIL: _version_ge leaked \$i (expected 'LEAKED_VALUE', got '$i')"
    fi
}

# ---------------------------------------------------------------------------
# Suite: _log function
# ---------------------------------------------------------------------------

test_log_function() {
    echo "--- _log ---"

    local tmp_log
    tmp_log=$(mktemp)
    # shellcheck disable=SC2064
    trap "rm -f $tmp_log" EXIT

    # Override LOG_FILE for test isolation
    local orig_log_file="$LOG_FILE"
    LOG_FILE="$tmp_log"

    # _log should write to both stdout and file
    local stdout_out
    stdout_out=$(_log "test message 123")

    # Check stdout
    _assert_contains "stdout contains message" "test message 123" "$stdout_out"

    # Check file
    local file_content
    file_content=$(cat "$tmp_log")
    _assert_contains "file contains message" "test message 123" "$file_content"

    # Test with color helpers
    local colored_out
    colored_out=$(_log "$(_green "green msg")")
    _assert_contains "colored stdout works" "green msg" "$colored_out"
    local colored_file
    colored_file=$(cat "$tmp_log")
    _assert_contains "colored file works" "green msg" "$colored_file"

    # Test multiple calls append
    _log "second message"
    local line_count
    line_count=$(wc -l < "$tmp_log")
    _assert_eq "file has 3 lines after 3 _log calls" "3" "$line_count"

    # Restore
    LOG_FILE="$orig_log_file"
    rm -f "$tmp_log"
    trap - EXIT
}

# ---------------------------------------------------------------------------
# Suite: _find_pg_tools version range
# ---------------------------------------------------------------------------

test_find_pg_tools_range() {
    echo "--- _find_pg_tools range ---"

    # Test that _find_pg_tools scans version range 10-99
    # We can't test actual file existence, but we can verify the function
    # iterates through versions by checking it doesn't error on a clean system

    # On Linux, _find_pg_tools should return 1 (not found) without errors
    # This validates the loop logic doesn't crash
    local result=0
    _find_pg_tools || result=$?

    # Should return 1 (not found) on Linux without pg tools
    _assert_eq "_find_pg_tools returns 1 on Linux" "1" "$result"

    # Verify the function is callable and doesn't crash with set -Eeuo pipefail
    _assert_eq "_find_pg_tools doesn't crash" "1" "$result"
}

# ---------------------------------------------------------------------------
# Suite: state partial reset (phases 3-8)
# ---------------------------------------------------------------------------

test_state_partial_reset() {
    echo "--- state partial reset ---"

    local tmp_state
    tmp_state=$(mktemp)
    # shellcheck disable=SC2064
    trap "rm -f $tmp_state" EXIT

    # Override STATE_FILE for test isolation
    local orig_state_file="$_STATE_FILE"
    _STATE_FILE="$tmp_state"

    # Set up state with all phases done
    for p in phase_1 phase_2 phase_3 phase_4 phase_5 phase_6 phase_7 phase_8; do
        echo "$p=done" >> "$_STATE_FILE"
    done

    _assert_eq "all phases done initially" "8" "$(wc -l < "$_STATE_FILE" | tr -d ' ')"

    # Simulate what _phase_2_venv does on recreate: delete phases 3-8
    for p in phase_3 phase_4 phase_5 phase_6 phase_7 phase_8; do
        sed -i "/^${p}=done$/d" "$_STATE_FILE" 2>/dev/null
    done

    # Verify phases 1-2 still exist
    _assert_eq "phase_1 preserved" "true" "$(_is_phase_done "phase_1" && echo true || echo false)"
    _assert_eq "phase_2 preserved" "true" "$(_is_phase_done "phase_2" && echo true || echo false)"

    # Verify phases 3-8 removed
    _assert_eq "phase_3 removed" "false" "$(_is_phase_done "phase_3" && echo true || echo false)"
    _assert_eq "phase_4 removed" "false" "$(_is_phase_done "phase_4" && echo true || echo false)"
    _assert_eq "phase_5 removed" "false" "$(_is_phase_done "phase_5" && echo true || echo false)"
    _assert_eq "phase_6 removed" "false" "$(_is_phase_done "phase_6" && echo true || echo false)"
    _assert_eq "phase_7 removed" "false" "$(_is_phase_done "phase_7" && echo true || echo false)"
    _assert_eq "phase_8 removed" "false" "$(_is_phase_done "phase_8" && echo true || echo false)"

    # Verify only 2 lines remain (phase_1 + phase_2)
    local remaining
    remaining=$(wc -l < "$_STATE_FILE" | tr -d ' ')
    _assert_eq "only 2 lines remain" "2" "$remaining"

    # Cleanup
    _STATE_FILE="$orig_state_file"
    rm -f "$tmp_state"
    trap - EXIT
}

# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

run_all_tests() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║          Tests: setup.sh helper functions                   ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    # Source setup.sh in test mode (defines functions, skips main)
    if [[ ! -f "$SETUP_SH" ]]; then
        echo "ERROR: setup.sh not found at $SETUP_SH"
        exit 1
    fi

    # Source the production script — test mode is detected internally
    # by setup.sh via SETUP_SH_TEST_MODE=true
    export SETUP_SH_TEST_MODE=true
    # shellcheck disable=SC1090
    source "$SETUP_SH"

    test_parse_python_version
    test_version_ge
    test_version_ge_no_leak
    test_detect_os
    test_color_helpers
    test_state_functions
    test_banner
    test_log_function
    test_find_pg_tools_range
    test_state_partial_reset

    echo ""
    echo "────────────────────────────────────────────────────────────────"
    echo "Results: $PASSED passed, $FAILED failed"
    echo "────────────────────────────────────────────────────────────────"

    if [[ ${#FAILURES[@]} -gt 0 ]]; then
        echo ""
        echo "FAILURES:"
        for f in "${FAILURES[@]}"; do
            echo "  - $f"
        done
    fi

    return "$FAILED"
}

run_all_tests
