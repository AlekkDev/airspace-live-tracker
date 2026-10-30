# 10 · Roadmap

Task-level status for every milestone: [11 Tasks](11-tasks.md). Weeks are counted from project start (2026-10-27). **Collection starts in week 0**, because the unusual-traffic baseline needs ≥ 3 weeks of history and the ETA model needs as many observed arrivals as possible.

## Milestones (core)

| Milestone | Weeks | Deliverables | Done when |
|---|---|---|---|
| **M0 · Foundations** | 0–1 | Repo + docs. OpenSky account and API client; read OpenSky's terms. Decide O1. Collector v0 in spool-only mode on pc-daniel via Task Scheduler, including the daily flight-list task. Request the Oracle VM | pc-daniel produces a spool file every 90 s for 48 h; yesterday's flight lists arrive; measured rows/day and spool file sizes are written into [01](01-architecture.md#sizing); VM obtained, or fallback ordered by the end of week 1 |
| **M1 · Platform** | 1–2 | VM with Tailscale (Cloudflare and Caddy wait until before a public launch, [D3](11-tasks.md#decided-while-building)); pinned Timescale image; migrations **without** the compression policy; OurAirports seed (`ref.airports`, `ref.runways`); ingest-api + collector admin CLI; uploader drains the backlog; spool compaction and R2 archive upload; `agg_backfill_refresh`; then the compression-policy migration; Grafana ops dashboards (externally shared); CI and deploy; daily backup | Backlog ingested and aggregated; compression policy merged after the drain; Grafana shows rows/min, slot coverage and gaps; the local dev command works; a restore drill from R2 succeeds |
| **M2 · Live map** | 2–4 | public-api `/live/*`, `/aircraft/*`, `/events`, `/stats`, `/health`, SSE; stream-worker squawk and go-around events; `metar_fetch`; web app with map, smooth motion, aircraft card, trails, events panel; Cloudflare rate limit, firewall and CORS | Public URL shows smooth live traffic; merge to `main` deploys; every item in [01 Networking and security](01-architecture.md#networking-and-security) is in place before the URL is shared |
| **M3 · Curated data** | 3–5 | `flights_sessionizer`, `flight_labels_merge`, `routes_refresh`; `ref_refresh` (takes over airports and runways; first load of aircraft, airlines, countries, H3 → country); `metar_backfill`; DQ checks; `collector_gap_check`; record the aircraft-database licence in [02](02-data-sources.md#reference-data) | `core.flights` has observed arrivals for LOWW/LZIB/LHBP with `height_method` set; route lookup populated; DQ table green |
| **M4 · ML** | 4–6 | Unusual-traffic v1 + heatmap + anomaly events; ETA v1 + arrivals board; destination route lookup in the card; MLflow + weekly `train_eta`; `ops.model_runs` + public Models dashboard; model cards | ETA p50 MAE beats B1 on the hold-out; anomaly model card reports injection recall and events/day; destination accuracy vs baseline reported |
| **M5 · LLM** | 5–7 | Briefing job + panel; chat with guardrails; golden-set eval in CI | ≥ 80% eval accuracy; briefing number check passes on all fixtures |
| **M6 · Portfolio polish** | 7–8 | README with architecture diagram + demo video; model cards final; final report | A stranger can understand and run the project from the README |

## Stretch

Started only when every M0–M5 "done when" is met, in this order. When one starts, change its status here in the same PR.

| # | Item | Spec | Status |
|---|---|---|---|
| S1 | Destination re-ranker | [06](06-ml.md#stretch-kinematic-re-ranker) | not started |
| S2 | Unusual-traffic v2 | [06](06-ml.md#1--unusual-traffic-anomaly-detection) | not started |
| S3 | Holding-pattern events | [04](04-pipelines.md#stretch-holding-detection) | not started |
| S4 | Self-hosted PMTiles basemap | [08](08-frontend.md#stack) | not started |

Level 2 (own ADS-B receiver) is out of scope ([ADR-0002](adr/0002-source-agnostic-ingestion.md)).

## Work split

Two tracks meet at the [API contract](05-api-contract.md) and the [data model](03-data-model.md):

| Track A · Data platform | Track B · Product & ML |
|---|---|
| collector, ingest-api, DB + migrations | public-api, web app, map layers |
| orchestrator jobs, DQ, Grafana | ETA + destination, MLflow, model cards |
| CI/CD, VM, backups | LLM briefing + chat + eval |

The unusual-traffic model is shared: Track A builds the aggregates and baseline, Track B builds scoring, the heatmap and evaluation. Both of us review each other's PRs.

## Open decisions

| # | Decision | Deadline | Until decided |
|---|---|---|---|
| O1 | Who owns Track A and Track B | Kickoff, week 0 | — |
| O5 | Project name and domain | Before a public launch ([D3](11-tasks.md#decided-while-building)) | Working title "Airspace Monitor" |
| O7 | Dedicated low-power collector device (Raspberry Pi or used mini-PC) | Product owner approval | Collectors run on the Windows PCs via Task Scheduler |

## Decided

| Topic | Decision |
|---|---|
| Orchestrator | Dagster |
| Basemap | CARTO Dark Matter; PMTiles is stretch S4 |
| Polling | One collector polls the whole world every 90 s. A regional high-frequency plan was rejected: it needs 6,240 credits/day against 4,000 |
| Hosting | Oracle Cloud Always Free, Contabo fallback ([ADR-0004](adr/0004-hosting-oracle-free-tier.md)) |
| Chat limits | 10 questions/hour per IP, 200/day globally, $40/month Anthropic spend limit |
| Model tracking | MLflow stays private; results are public through Grafana and model cards |
| Retraining | Only in Dagster on the server |

## Links

- Interactive UI mockup (mock data, simulated motion): https://claude.ai/artifact/KThDqgF13EAiuWDvA296Xv. Private until shared from its Share menu.
- Project intent: [CloudAI-project-intent.pdf](CloudAI-project-intent.pdf)
