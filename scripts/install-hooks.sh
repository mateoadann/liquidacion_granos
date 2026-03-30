#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

install -m 0755 "$ROOT_DIR/.githooks/pre-push" "$ROOT_DIR/.git/hooks/pre-push"

echo "Hook instalado: .git/hooks/pre-push"
