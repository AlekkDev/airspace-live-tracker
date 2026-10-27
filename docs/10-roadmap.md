# 10 · Roadmap

Weeks are counted from project start. **Collection starts in week 0** because the anomaly model needs ≥ 3 weeks of history and the ETA model needs as many arrivals as we can get.

| Milestone | Weeks | Deliverables | Done when |
|---|---|---|---|
| **M0 · Foundations** | 0–1 | GitHub repo + these docs; OpenSky accounts + API clients for both of us; collector v0 in **spool-only mode** running on both PCs (offsets 0 s / 45 s) | Both PCs produce a spool file every 90 s for 48 h |
| **M1 · Platform** | 1–2 | VPS + Caddy + Timescale + migrations; ingest-api; uploader backfills the spool; Grafana ops dashboard; CI (lint/test/build) | Backlog ingested; Grafana shows rows/min and gaps; `docker compose up` works locally |
| **M2 · Live map** | 2–4 | public-api `/live/*`, `/aircraft/*`, SSE; web app with deck.gl map, dead reckoning, aircraft card, trails; squawk events; deploy pipeline | Public URL shows smooth live traffic; merge to `main` deploys |
| **M3 · Curated data** | 3–5 | flights sessionizer; METAR; reference data; Zenodo → Parquet → `ref.callsign_routes`; Dagster jobs + job_runs; DQ checks | `core.flights` has labelled arrivals for LOWW/LZIB/LHBP; DQ table green |
| **M4 · ML** | 4–6 | anomaly v1 + heatmap layer; destination v1; ETA v1 + arrivals board; MLflow registry + weekly retrain | Models beat baselines on the hold-out; metrics visible in MLflow |
| **M5 · LLM** | 5–7 | briefing job + panel; chat with guardrails; golden-set eval in CI | ≥ 80% eval accuracy; no hallucinated numbers in briefing checks |
| **M6 · Portfolio polish** | 7–8 | README with architecture diagram + demo GIF/video; public Grafana and MLflow; model cards; final report | A stranger can understand and run the project from the README |
| **Level 2** | later | Raspberry Pi + RTL-SDR + antenna; readsb; feed OpenSky; `local_adsb` source; 1 Hz regional stream | Local region updates every second on the map |

## Suggested work split (to confirm, O1)

Two tracks meet at the [API contract](05-api-contract.md) and the [data model](03-data-model.md):

| Track A · Data platform | Track B · Product & ML |
|---|---|
| collector, ingest-api, DB + migrations | public-api, web app, map layers |
| orchestrator jobs, DQ, Grafana | ETA + destination models, MLflow |
| CI/CD, VPS, backups | LLM briefing + chat + eval |

The anomaly model is shared: Track A builds the aggregates and baseline, Track B builds the heatmap and evaluation. Both of us review each other's PRs, so we both understand the whole system before interviews.

## Open decisions

| # | Decision | Options | Recommendation |
|---|---|---|---|
| O1 | Who owns which track | A/B as above | Decide in kickoff |
| O2 | Orchestrator | Dagster · plain APScheduler service | **Dagster**: its asset graph and run history are a strong visual for DE interviews; fits in 8 GB RAM |
| O3 | Basemap | CARTO Dark Matter · self-hosted Protomaps PMTiles | CARTO now, PMTiles in M6 if time |
| O4 | Polling plan | 2 × global offset 45 s · global 180 s + Central Europe box 60 s | Start with 2 × global; measure ETA data volume in M3 and revisit |
| O5 | Project name + domain | "Airspace Monitor" (working) | Pick before M2 (affects subdomains) |
| O6 | Public chat limits | per-IP + global daily cap | 10/h per IP, global cap sized to a fixed monthly budget |

## Links

- Interactive UI mockup (mock data, simulated motion): https://claude.ai/artifact/KThDqgF13EAiuWDvA296Xv. Private until shared from its Share menu.
- Project intent: [CloudAI-project-intent.pdf](CloudAI-project-intent.pdf)
