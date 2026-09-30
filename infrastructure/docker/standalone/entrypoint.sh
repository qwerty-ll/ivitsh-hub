#!/bin/bash
# Runs the whole portal in one container: backend on 127.0.0.1:8000 and nginx on :8080.
# The container stops as soon as either exits, so `docker compose ps` never shows a half-dead portal.
set -euo pipefail
trap 'kill $(jobs -p) 2>/dev/null; wait; exit 0' TERM INT

DATA=/app/data

# A stable JWT secret per data volume: sessions survive restarts, and nothing secret lives in the image.
if [ -z "${SECRET_KEY:-}" ]; then
  [ -s "$DATA/secret_key" ] || (umask 077; python -c 'import secrets; print(secrets.token_urlsafe(48))' > "$DATA/secret_key")
  SECRET_KEY=$(cat "$DATA/secret_key")
  export SECRET_KEY
fi

# Files attached to tasks and announcements live in the data volume too
export UPLOAD_DIR="${UPLOAD_DIR:-$DATA/uploads}"

uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1 &

healthy=0
for _ in $(seq 60); do
  if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)" 2>/dev/null; then
    healthy=1
    break
  fi
  sleep 1
done
if [ "$healthy" != 1 ]; then
  echo "Backend did not become healthy in 60s, see the log above." >&2
  exit 1
fi

nginx -e stderr -g 'daemon off;' &

echo "Portal is up: http://localhost:${PORT:-8080}"

set +e
wait -n
status=$?
echo "A portal process exited with status $status, stopping the container." >&2
kill $(jobs -p) 2>/dev/null
wait
exit "$status"
