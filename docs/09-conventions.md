# 09 · Conventions

## Repository layout (monorepo)

```
airspace-live-tracker/
├── AGENTS.md / CLAUDE.md      # instructions for AI coding assistants (Cursor, Claude Code)
├── README.md
├── docs/                      # these grounding docs + adr/
├── collector/                 # P1: Python package + Dockerfile (amd64 + arm64)
├── services/
│   ├── ingest/                # P2: FastAPI ingest-api
│   ├── api/                   # public-api (REST, SSE, chat)
│   ├── stream/                # P3: stream-worker
│   ├── orchestrator/          # P4: Dagster definitions (jobs, schedules, assets)
│   └── llm/                   # prompts/, eval/, shared Claude client
├── ml/                        # feature code, training, model cards, notebooks/
├── libs/airspace_common/      # shared Python: settings, db, h3 helpers, schemas
├── db/
│   ├── migrations/            # dbmate SQL migrations
│   ├── seeds/                 # reference data loaders, fixture dump for tests
│   └── llm_views.md           # data dictionary used by the chat prompt
├── web/                       # React app
├── infra/
│   ├── compose.yml            # full VPS stack
│   ├── compose.dev.yml        # local dev overrides
│   ├── caddy/Caddyfile
│   └── grafana/               # provisioned datasources + dashboards (JSON)
└── .github/workflows/         # ci.yml, deploy.yml, retrain.yml, llm-eval.yml
```

## Tooling

| Area | Choice |
|---|---|
| Python | 3.12, **uv** (workspace across `collector`, `services/*`, `ml`, `libs/*`), ruff (lint + format), pytest, mypy on `libs/` |
| JS | Node 22 LTS, **pnpm**, ESLint, Prettier, Vitest |
| DB migrations | **dbmate**, plain SQL, forward-only; every migration has a test in CI against a Timescale container |
| Containers | One Dockerfile per service, multi-stage, non-root user; images `ghcr.io/<org>/airspace-<service>` |
| Local dev | `docker compose -f infra/compose.yml -f infra/compose.dev.yml up` gives the full stack with a seeded DB |

## Git workflow

- `main` is always deployable. Work happens on short-lived branches: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- Every change goes through a pull request and needs one approval from the other teammate. Squash-merge.
- Commit messages follow Conventional Commits (`feat(collector): add spool compaction`).
- CI on each PR:
  - lint, type-check and tests (Python + web),
  - migration test,
  - Docker build,
  - LLM eval when `services/llm/**` or `db/llm_views.md` changes.
- A change to a table, endpoint or pipeline updates the matching doc in `docs/` **in the same PR**.
- Larger decisions get an ADR: `docs/adr/NNNN-title.md` with Context / Decision / Consequences.

## Configuration & secrets

- All config comes from environment variables, read via `pydantic-settings` in `libs/airspace_common/settings.py`.
- `.env.example` lists every variable with a comment. Real `.env` files are git-ignored.
- Secrets: OpenSky client secrets stay on each collector's machine. The VPS `.env` holds DB passwords, collector key hashes and the Anthropic key. CI uses GitHub Actions secrets.
- Never log secrets or full request bodies from collectors.

## Code conventions

- Time is always UTC `datetime` with tzinfo. Never naive datetimes.
- Units are SI internally. Variable names carry units when ambiguous (`alt_m`, `vel_ms`).
- `icao24` is lower-case hex. Callsigns are trimmed.
- SQL lives in `.sql` files or clearly named constants, never assembled from user input. The only dynamic SQL is the guarded LLM path.
- Every job is idempotent and takes an explicit time window.
- Logs are structured JSON (`structlog`) with `service`, `job`, `batch_id` where relevant.

## Working with AI assistants

Both of us use AI coding assistants (Cursor, Claude Code). `AGENTS.md` at the repo root is the shared instruction file. It points to these docs, so the assistant follows the agreed schema and contracts. When an assistant proposes a change that contradicts a doc, either the doc is updated deliberately in the same PR or the change is rejected.
