#!/bin/sh
set -eu

identity="$(python -m backend.app.container_identity)" || exit $?
puid="${identity%%:*}"
pgid="${identity##*:}"

if ! groupmod --non-unique --gid "$pgid" prefine; then
  echo "PreFine startup error: could not set prefine PGID to $pgid" >&2
  exit 70
fi

if ! usermod --non-unique --uid "$puid" --gid "$pgid" prefine; then
  echo "PreFine startup error: could not set prefine PUID to $puid" >&2
  exit 70
fi

if ! mkdir -p /data || ! chown -R "$puid:$pgid" /data; then
  echo "PreFine startup error: cannot prepare /data; check PREFINE_DATA_DIR, PUID=$puid and PGID=$pgid" >&2
  exit 73
fi

if [ "$#" -gt 0 ]; then
  exec gosu "$puid:$pgid" "$@"
fi

exec gosu "$puid:$pgid" sh -c '
  set -e
  python -m alembic -c backend/alembic.ini upgrade head
  exec python -m uvicorn backend.app.main:create_app \
    --factory \
    --host 0.0.0.0 \
    --port 8000 \
    --no-proxy-headers \
    --workers 1
'
