# English Reps backend

FastAPI + PostgreSQL API for the React English Reps frontend: account registration/login,
private progress across devices and server-graded vocabulary/listening events.
The catalog contains all original 1,000 vocabulary entries and 30 original listening questions.

## Run the complete project

Clone the repositories side by side and select matching feature branches until their MRs merge:

```sh
git clone https://github.com/english-reps/english-reps-backend.git
git clone https://github.com/english-reps/english-reps-frontend.git
cd english-reps-backend
git switch feature/account-progress-sync
git -C ../english-reps-frontend switch feature/account-progress-sync
cp .env.example .env
# Edit POSTGRES_PASSWORD and the matching DATABASE_URL password in .env.
docker compose --profile dev up --build --wait
```

Open `http://localhost:3007`: Vite forwards `/api` to FastAPI. Create an account, finish an
exercise, then log in from another browser to see the same progress. The database has no host port.
The backend owns `compose.yml`; set `FRONTEND_PATH` if the frontend is in another directory.

For the Nginx setup with compiled assets (still local HTTP, not an Internet deployment):

```sh
docker compose --profile dev stop frontend
docker compose --profile prod up --build --wait
# Open http://localhost:8080
python scripts/smoke.py http://localhost:8080
docker compose --profile prod down
```

Do not add `-v` to `down` unless you intentionally want to erase the database volume.
Migrations run once after database health and before API readiness. Vocabulary and listening
catalogs live in `data/vocabulary.json` and `data/listening.json` and are loaded and validated
from disk by the API (PostgreSQL only stores accounts, sessions, rate-limit counters and user
progress). Vite/Nginx proxy from one browser origin, so CORS is not opened.
API trusts forwarded client IPs only because it is not published to the host; both included
proxies overwrite X-Forwarded-For. Keep the API isolated behind those proxies.

## Develop and check the backend

Use Python 3.12+ and uv 0.13.6. With a local PostgreSQL URL in the environment:

```sh
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The checked-in example uses `db` for the Compose network; change to your actual host for a
non-container process. Unit/integration tests require a **separate** database with `test` in its name:

```sh
export DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@localhost:5432/english_reps_test'
export TEST_DATABASE_URL="$DATABASE_URL"
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic check
uv run ruff check .
uv run mypy app
uv run pytest -q
```

Tests truncate account data in that test database and use real PostgreSQL, not SQLite.
They check CSRF, session rotation/expiry/revocation, ownership, cross-device reads, server grading,
concurrent retries/atomic counters, card rating toggles, file-based catalog validation and auth rate
limiting. OpenAPI is available at `/docs` on the API service. The first migration keeps immutable
schema/catalog snapshots so future model changes do not alter old migrations. New migrations belong
in `alembic/versions/`. To add or edit questions, update `data/vocabulary.json` or
`data/listening.json` directly and keep existing IDs stable.

Corporate build proxies can pass their trusted CA as an optional BuildKit `build_ca` secret to
both Dockerfiles. This preserves TLS verification; no CA or credentials are baked into the image.

## Delivery and branch policy

`master`: formal releases; `develop`: integration; `feature/*`: reviewed work. Use squash merging
for independent features; for the stacked frontend MRs merge in dependency order and retarget the
next MR before merging (do not squash away a stacked base without updating its dependents).
GitHub Actions runs Ruff, mypy, real PostgreSQL migrations/tests, Compose validation and an image build.
Recommended required branch check: `backend-checks`. Configure this in GitHub Settings → Rules →
Rulesets → target `master`/`develop` → Require a pull request / Require status checks.
Rulesets are a repository setting; this MR does not enable them.

Production hosting is deliberately undecided. Before Internet deployment, configure HTTPS,
`APP_ENV=production`, `COOKIE_SECURE=true`, exact HTTPS `ALLOWED_ORIGINS`, strong database credentials,
backups/restore tests, monitoring and an email/password-reset policy. Production validation rejects
insecure cookies and HTTP origins. The existing `chatgpt.site` static website is unchanged.

See [architecture](docs/architecture.md) and [API contract](docs/api-contract.md), mirrored in the frontend.

## Render staging deployment

See [Render staging guide](docs/render-staging.md) for hosted HTTPS URLs without renting a server.
The backend repo owns `render.yaml`; both services follow `develop` after CI passes.
This requires a Render account and GitHub repository authorization; a committed YAML file alone
does not create a running site. The free PostgreSQL database expires after 30 days.
