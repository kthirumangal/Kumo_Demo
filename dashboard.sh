#!/usr/bin/env bash
#
# Launch the KumoRFM dashboard (consolidated view).
#
#   ./dashboard.sh                 serve on http://localhost:8080
#   ./dashboard.sh --port 9000
#
# Updated 2026-10-20. No Docker, no VPN, no SDK patching: the official
# kumo-relational-client is on public PyPI, ships macOS arm64 wheels, and
# speaks `kumo-relational` natively. The Sep 7 container path that rewrote the
# model id inside the image is kept in legacy/.

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV=".venv"
PORT="${KUMO_PORT:-8080}"
[ "${1:-}" = "--port" ] && { PORT="$2"; shift 2; }

[ -f .env ] && { set -a; . ./.env; set +a; }
URL="${KUMO_URL:-${KUMORFM_URL:-https://rfm-nim.dev.kumoai.cloud}}"
KEY="${KUMO_API_KEY:-${KUMORFM_API_KEY:-}}"

if [ -z "$KEY" ]; then
  echo "No API key. Put KUMO_API_KEY in .env next to this script."
  exit 1
fi

# Keep the Sep 7 habit of asking the endpoint what it serves, rather than
# assuming. The client targets kumo-relational; anything else is worth knowing
# BEFORE the dashboard is on a projector.
detect_model_id() {
  python3 - "$URL" "$KEY" <<'PY' 2>/dev/null
import json, sys, urllib.request
url, key = sys.argv[1].rstrip("/") + "/v1/models", sys.argv[2]
req = urllib.request.Request(url, headers={"X-API-Key": key} if key else {})
try:
    d = json.load(urllib.request.urlopen(req, timeout=12))
    ids = [m.get("id") for m in d.get("data", []) if isinstance(m, dict)]
    rel = [i for i in ids if i and i != "tabicl"]
    print(rel[0] if rel else "")
except Exception:
    print("")
PY
}

MID="$(detect_model_id)"
if [ -z "$MID" ]; then
  echo "!! could not read $URL/v1/models — check the network and the key."
  exit 1
elif [ "$MID" = "kumo-relational" ]; then
  echo "==> endpoint serves: $MID  (matches the client)"
else
  echo "!! endpoint serves '$MID', but kumo-relational-client speaks 'kumo-relational'."
  echo "   Predictions will fail. Ask in #kumo-usecase-intake which client matches,"
  echo "   or fall back to legacy/dashboard_docker.sh (Docker + VPN)."
  exit 2
fi

if [ ! -d "$VENV" ]; then
  echo "==> Creating $VENV (first run only)"
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      v=$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
      case "$v" in 3.10|3.11|3.12|3.13) PY="$c"; break;; esac
    fi
  done
  [ -z "$PY" ] && { echo "Need Python 3.10-3.13."; python3 -V; exit 1; }
  echo "    using $PY ($("$PY" -V 2>&1))"
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  echo "==> Installing client + FastAPI (public PyPI)"
  "$VENV/bin/pip" install --quiet \
    "kumo-relational-client[relational]" fastapi uvicorn pandas
fi

export KUMO_URL="$URL" KUMO_API_KEY="$KEY" KUMO_PORT="$PORT"
echo "==> key ${#KEY} chars · endpoint $URL"
echo "==> dashboard: http://localhost:$PORT/"
exec "$VENV/bin/python" server.py
