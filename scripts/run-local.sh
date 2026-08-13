#!/usr/bin/env bash
# Bring up the local stack (api + worker) with Docker Compose. See SETUP.md §A (Local).
# Requires: Docker + Compose, a .env (RESUMAKER_API_TOKEN + LLM), and data/profile/profile.json.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "!! copy .env.example to .env and fill it first"; exit 1; }
exec docker compose -f deploy/docker-compose.split.yml up --build "$@"
