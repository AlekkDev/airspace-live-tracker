# Instructions for AI coding assistants

Shared by Cursor and Claude Code. Project overview: [README.md](README.md).

## Source of truth

The docs in `docs/` define the system. Read the relevant one before changing code:

- Tables, columns, roles → `docs/03-data-model.md`
- Endpoints and payloads → `docs/05-api-contract.md`
- Collector, ingest, scheduled jobs → `docs/04-pipelines.md`
- Models and metrics → `docs/06-ml.md`; LLM features → `docs/07-llm.md`
- UI, layers, colours → `docs/08-frontend.md`
- Repo layout, tooling, git workflow → `docs/09-conventions.md`
- Scope (core vs stretch), milestones → `docs/00-overview.md`, `docs/10-roadmap.md`

If a change contradicts a doc, stop and say so. Do not silently diverge. When a change is agreed, update the doc in the same change.

## Rules

- UTC `timestamptz` everywhere; SI units internally (`alt_m`, `vel_ms`); `icao24` lower-case hex.
- Every job and ingest path is idempotent and takes an explicit time window.
- Never commit secrets. Config comes from env vars via `libs/airspace_common/settings.py`; document new vars in `.env.example`.
- Migrations are forward-only SQL in `db/migrations/` (dbmate) and must work with the code already running.
- Build only core features. Stretch items wait until `docs/10-roadmap.md` marks them started; Level 2 is out of scope.
- Python: uv, ruff, pytest. Web: pnpm, TypeScript strict, ESLint/Prettier.
- Write tests with the code. Run lint and tests before declaring work done.
- Keep the OpenSky attribution visible in the UI; the data is for non-commercial use only.
- Conventional Commits; one teammate reviews every PR.
