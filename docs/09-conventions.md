# 09 · Conventions

## Repository layout (monorepo)

```
airspace-live-tracker/
├── AGENTS.md / CLAUDE.md      # instructions for AI coding assistants (Cursor, Claude Code)
├── README.md
├── docs/                      # these grounding docs + adr/
├── collector/                 # P1: Python package, Windows Task Scheduler setup script, Dockerfile (amd64 + arm64)
├── services/
│   ├── ingest/                # P2: FastAPI ingest-api (+ admin CLI for collector keys)
│   ├── api/                   # public-api (REST, SSE, chat)
│   ├── stream/                # P3: stream-worker
│   ├── orchestrator/          # P4: Dagster definitions (jobs, schedules, assets)
│   └── llm/                   # prompts/, eval/, shared Claude client
├── ml/                        # feature code, training, MODEL_CARD.md per model, notebooks/
├── libs/airspace_common/      # shared Python: settings, db, h3 helpers, altitude, schemas
├── db/
│   ├── migrations/            # dbmate SQL migrations
│   ├── seeds/                 # reference data loaders; fixture/ = small dump for tests and the LLM eval
│   └── llm_views.md           # data dictionary used by the chat prompt
├── web/                       # React app
├── infra/
│   ├── compose.yml            # full server stack
│   ├── compose.dev.yml        # local dev overrides (seeded DB, no Caddy/TLS)
│   ├── deploy.sh              # pull → migrate → up
│   ├── caddy/Caddyfile
│   └── grafana/               # provisioned datasources + dashboards (JSON)
└── .github/workflows/         # ci.yml, deploy.yml, llm-eval.yml
```

## Tooling

| Area | Choice |
|---|---|
| Python | 3.12, **uv** workspace (`collector`, `services/*`, `ml`, `libs/*`), ruff (lint + format), pytest, mypy on `libs/`. UUIDv7 via the `uuid6` package (`uuid6.uuid7()`) |
| JS | Node 24 LTS, **pnpm**, TypeScript strict, ESLint, Prettier, Vitest |
| DB access | **psycopg 3** with `psycopg_pool`; argon2id via `argon2-cffi` |
| DB migrations | **dbmate**, plain SQL, forward-only. Every migration runs in CI against the pinned Timescale image |
| Containers | One Dockerfile per service, multi-stage, non-root user, built for `linux/amd64` and `linux/arm64`; images `ghcr.io/<org>/airspace-<service>` |
| Local dev | `docker compose -f infra/compose.yml -f infra/compose.dev.yml up` starts the full stack with the fixture database |

## Git workflow

- `main` is always deployable. Short-lived branches: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- Every change goes through a pull request with one approval from the other teammate. Squash-merge.
- Conventional Commits (`feat(collector): add spool compaction`).
- A change to a table, endpoint, job or pipeline updates the matching doc in `docs/` **in the same PR**.
- Larger decisions get an ADR: `docs/adr/NNNN-title.md` with Context / Decision / Consequences.

## CI/CD

| Workflow | Trigger | Steps |
|---|---|---|
| `ci.yml` | every PR and push | ruff, mypy, pytest; ESLint, tsc, Vitest; migration test (apply all migrations to an empty pinned Timescale container, then run the compressed-chunk insert test); Docker build for both architectures |
| `llm-eval.yml` | PRs touching `services/llm/**`, `db/llm_views.md`, `db/migrations/**`, `db/seeds/fixture/**` | Golden-set eval and briefing number check against the fixture DB ([07](07-llm.md#3--evaluation-ci)) |
| `deploy.yml` | push to `main` | Build and push multi-arch images, deploy over Tailscale ([01](01-architecture.md#deployment)) |

Model training runs only in Dagster on the server, never in GitHub Actions.

## Migrations

- Forward-only SQL; never edit a merged migration.
- Migrations run before new code starts ([01](01-architecture.md#deployment)), so each one must work with the code already running: add first, remove in a later release.
- The raw compression policy is its own migration, merged only after the M1 backlog drain ([03](03-data-model.md#rawstate_vectors-hypertable)).
- CI includes a test that inserts rows, some duplicates, into a compressed chunk with `ON CONFLICT DO NOTHING` and asserts every non-duplicate row is stored (guards against timescale/timescaledb#7672).

## Configuration and secrets

- All config comes from environment variables, read via `pydantic-settings` in `libs/airspace_common/settings.py`.
- `.env.example` lists every variable with a comment. Real `.env` files are git-ignored.
- Where each secret lives is defined in [01](01-architecture.md#networking-and-security). Collector keys are stored server-side only as hashes in `ops.collectors`, never in `.env`.
- Never log secrets, client IPs or full request bodies.

## Code conventions

- Time is always UTC `datetime` with tzinfo. Never naive datetimes.
- Units are SI internally. Variable names carry units when ambiguous (`alt_m`, `vel_ms`).
- `icao24` is lower-case hex. Callsigns are trimmed; empty is `None`.
- SQL lives in `.sql` files or named constants and is never assembled from user input. The only dynamic SQL is the guarded chat path ([07](07-llm.md#guardrails)).
- Every job is idempotent and takes an explicit time window ([04](04-pipelines.md#p4--orchestrated-jobs)).
- Logs are structured JSON (`structlog`) with `service`, `job`, `batch_id` where relevant.
- Stretch features ([00](00-overview.md#stretch-only-after-the-core-ships)) are not built until the roadmap promotes them.

## Working with AI assistants

Both of us use AI coding assistants (Cursor, Claude Code). `AGENTS.md` at the repo root is the shared instruction file and points to these docs. When an assistant proposes a change that contradicts a doc, either the doc is updated deliberately in the same PR or the change is rejected.
