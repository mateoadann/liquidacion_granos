#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_COMPOSE="${DOCKER_COMPOSE:-docker compose}"
WEB_SERVICE="${WEB_SERVICE:-backend}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-frontend}"

echo "[pre-push] backend compile sanity"
$DOCKER_COMPOSE exec -T "$WEB_SERVICE" python -m compileall app tests >/dev/null

echo "[pre-push] backend quick tests"
$DOCKER_COMPOSE exec -T "$WEB_SERVICE" pytest tests/unit -q

echo "[pre-push] frontend typecheck"
$DOCKER_COMPOSE exec -T "$FRONTEND_SERVICE" npx tsc --noEmit

echo "[pre-push] quick checks OK"
