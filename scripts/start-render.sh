#!/bin/sh
# Free Render services don't have pre-deploy jobs; start only after migration succeeds.
set -eu
python -c 'import os; p=int(os.getenv("PORT", "10000")); assert 1 <= p <= 65535, "Invalid PORT"'

attempt=1
max_attempts=5
until alembic upgrade head; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "alembic upgrade head failed after ${max_attempts} attempts" >&2
        exit 1
    fi
    delay=$((attempt * 2))
    echo "alembic upgrade head attempt ${attempt}/${max_attempts} failed; retrying in ${delay}s..." >&2
    sleep "$delay"
    attempt=$((attempt + 1))
done

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --proxy-headers --forwarded-allow-ips '*'
