#!/bin/sh
set -eu

python -m alembic -c backend/alembic.ini upgrade head
exec python -m uvicorn backend.app.main:create_app \
  --factory \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1
