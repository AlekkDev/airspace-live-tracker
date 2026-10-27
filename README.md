# Airspace Monitor

> Working title. Team: Alek Hanušić & Dániel Csorba. MSc Cloud & AI project, built as a portfolio piece for AI / Data Engineering roles.

A live flight-tracking web app: a dark world map of every aircraft reported by the OpenSky Network, a data platform that stores and models the traffic, ML models (airspace anomalies, arrival-time and destination prediction) and an LLM layer that writes airspace briefings and answers questions by querying the database.

## Start here

| Doc | What it answers |
|---|---|
| [00 Overview](docs/00-overview.md) | Why we build this, scope, levels, success criteria, glossary |
| [01 Architecture](docs/01-architecture.md) | Components, deployment, networking, security, cost |
| [02 Data sources](docs/02-data-sources.md) | OpenSky, Zenodo, METAR, reference data: fields, limits, licences |
| [03 Data model](docs/03-data-model.md) | Database schemas, tables, retention, roles |
| [04 Pipelines](docs/04-pipelines.md) | Collector, ingestion, scheduled jobs, data quality, failure handling |
| [05 API contract](docs/05-api-contract.md) | Every HTTP endpoint and payload: the frontend/backend boundary |
| [06 ML](docs/06-ml.md) | Anomaly detection, ETA, destination prediction, MLflow conventions |
| [07 LLM](docs/07-llm.md) | Briefing and text-to-SQL chat, guardrails, evaluation |
| [08 Frontend](docs/08-frontend.md) | Screens, map layers, visual spec, interaction |
| [09 Conventions](docs/09-conventions.md) | Repo layout, tooling, git workflow, config and secrets |
| [10 Roadmap](docs/10-roadmap.md) | Milestones, ownership, open decisions |
| [ADRs](docs/adr/) | Architecture decision records |

The original one-page intent is in [docs/CloudAI-project-intent.pdf](docs/CloudAI-project-intent.pdf).

## Rule for changes

These docs are the source of truth. A change to a schema, endpoint, or pipeline updates the matching doc in the same pull request.
