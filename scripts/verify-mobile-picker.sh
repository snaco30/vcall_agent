#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HTML="$ROOT/app/board.html"
JS="$ROOT/app/static/board.js"
BASE_URL="${BASE_URL:-http://127.0.0.1:7002}"

echo "== syntax =="
node --check "$JS"

echo "== static markers =="
rg -q "initBoardNavHeightObserver" "$JS"
rg -q "lockBodyScroll\\(\\{ forPicker: true \\}\\)" "$JS"
rg -q "mobileBoardPickerBarEl\\?\\.addEventListener" "$JS"
rg -q "board\\.js\\?v=1\\.0\\.006" "$HTML"
grep -Fq -- "--board-nav-height" "$HTML"
rg -q "z-index: 50" "$HTML"

echo "== live page markers =="
TMP_HTML="$(mktemp)"
TMP_JS="$(mktemp)"
trap 'rm -f "$TMP_HTML" "$TMP_JS"' EXIT
curl -fsS "$BASE_URL/board" -o "$TMP_HTML"
curl -fsS "$BASE_URL/static/board.js?v=1.0.006" -o "$TMP_JS"
rg -q "board\\.js\\?v=1\\.0\\.006" "$TMP_HTML"
rg -q "initBoardNavHeightObserver" "$TMP_JS"

echo "OK: mobile picker verification passed"
