#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[pre-push] backend compile sanity"
python3 -m compileall "$ROOT_DIR/backend/app" "$ROOT_DIR/backend/tests" >/dev/null

echo "[pre-push] backend quick tests"
python3 -m pytest "$ROOT_DIR/backend/tests/unit" -q

echo "[pre-push] frontend typecheck"
(
  cd "$ROOT_DIR/frontend"
  npx tsc --noEmit
)

echo "[pre-push] quick checks OK"
