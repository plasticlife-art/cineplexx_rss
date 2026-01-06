#!/usr/bin/env bash
set -euo pipefail

echo "[worker] starting scheduler"
exec /venv/bin/python -m cineplexx_rss.main
