#!/bin/sh
# Free Render services don't have pre-deploy jobs; start only after migration succeeds.
set -eu
python -c 'import os; p=int(os.getenv("PORT", "10000")); assert 1 <= p <= 65535, "Invalid PORT"'
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --proxy-headers --forwarded-allow-ips '*'
