# Airspace Monitor

> Working title. Team: Alek Hanušić & Dániel Csorba. MSc Cloud & AI project, also built as a portfolio piece for AI and Data Engineering roles.

A live map of every plane in the sky, with predictions and an AI assistant on top. We collect free flight data from the OpenSky Network, store it in the cloud, spot unusual traffic, predict arrival times for Vienna, Bratislava and Budapest, and let an AI summarise the airspace and answer questions about it.

## How it works

1. **Source:** OpenSky, a free, volunteer-run network that reports the position of aircraft worldwide.
2. **Collect:** two home PCs fetch every plane's position every 90 seconds, taking turns, so we get an update about every 45 seconds. They run at home because OpenSky blocks requests from data centres.
3. **Process:** a cloud server stores the positions, works out flights, spots unusual traffic and predicts arrivals.
4. **Show:** a public website with the live map, an arrival board, an alert feed, an AI summary and an AI chat.

## What we're building

**Must ship (core):**
- Data collection that survives outages: nothing is lost, only delayed.
- Live map with planes moving smoothly between updates, coloured by altitude.
- Unusual-traffic heatmap: areas that are busier or quieter than usual for that time of the week.
- Alert feed: emergencies, aborted landings, unusual traffic, collection gaps.
- Arrival board for Vienna, Bratislava and Budapest, with each arrival time shown as a range.
- A best guess of where each flight is going.
- AI airspace summary every 30 minutes, built only from facts in our database.
- AI chat that answers questions in plain English and shows the database query behind each answer.
- Public dashboards showing data collection health and model results.

**Maybe, only if time allows (stretch), in this order:**
1. A smarter destination guess that also uses the plane's direction and altitude.
2. A smarter unusual-traffic model.
3. Alerts for planes circling in holding patterns.
4. Self-hosted map tiles.

**Not planned:** our own antenna for faster local updates, spotting individual "unusual flights", airline schedules or delays, mobile apps, user accounts, or any commercial use.

## What we can't change (and how we handle it)

| Limit | What we do |
|---|---|
| OpenSky only sees what its volunteers' receivers hear, so a receiver going offline looks like a traffic drop | "Unusually quiet" areas are labelled as possibly a coverage gap |
| Planes don't broadcast where they're going | Destinations are shown as the top 3 guesses, labelled as estimates |
| We see each plane only every 45–90 seconds | Arrival times are shown as ranges, accurate to about a minute at best |
| No airline schedules or air-traffic-control data | Arrival times far from the airport have wider ranges |
| Collection depends on home internet | Gaps are shown openly on the dashboard and in the feed |
| The AI chat won't always be right | Every answer shows its query; we test it against a fixed question set and aim for 80% correct |

## What it costs

About **€5–15 a month**, plus electricity for the home PCs:
- Server: €0 on Oracle Cloud's free tier (backup option about €5).
- AI features: about $2–8, with a hard cap.
- Domain: about €1.
- Off-site backups: €0–2.
- Electricity for two PCs running all day: an estimated €8–50, under €2 once collection moves to a small dedicated device.

## Status

Week 0 of 8. The plan and the technical documents are done; collection starts first so the models have history to learn from. Milestones are in the [roadmap](docs/10-roadmap.md).

## For developers

The documents in `docs/` define the system, and code follows them. A change to a table, endpoint or pipeline updates the matching document in the same pull request.

| Doc | What it answers |
|---|---|
| [00 Overview](docs/00-overview.md) | Scope (core vs stretch), success criteria, data limits, glossary |
| [01 Architecture](docs/01-architecture.md) | Components, hosting, deployment, security, sizing, cost |
| [02 Data sources](docs/02-data-sources.md) | OpenSky, METAR, reference data: fields, limits, licences |
| [03 Data model](docs/03-data-model.md) | Databases, schemas, tables, retention, roles |
| [04 Pipelines](docs/04-pipelines.md) | Collector, ingest, stream worker, scheduled jobs, catch-up, data quality |
| [05 API contract](docs/05-api-contract.md) | Every HTTP endpoint and payload |
| [06 ML](docs/06-ml.md) | Unusual traffic, ETA, destination, MLflow conventions |
| [07 LLM](docs/07-llm.md) | Briefing, text-to-SQL chat, guardrails, evaluation |
| [08 Frontend](docs/08-frontend.md) | Screens, map layers, visual spec |
| [09 Conventions](docs/09-conventions.md) | Repo layout, tooling, CI/CD, migrations, secrets |
| [10 Roadmap](docs/10-roadmap.md) | Milestones, stretch order, open decisions |
| [ADRs](docs/adr/) | Architecture decision records |

The original one-page intent is in [docs/CloudAI-project-intent.pdf](docs/CloudAI-project-intent.pdf).

## Data and credits

- Flight data: [The OpenSky Network](https://opensky-network.org), free for research and non-commercial use. The attribution is always visible in the app.
- Historical routes: OpenSky COVID-19 flight dataset on Zenodo (CC BY 4.0), DOI [10.5281/zenodo.3737101](https://doi.org/10.5281/zenodo.3737101).
- Airports and runways: [OurAirports](https://ourairports.com) (public domain).
- Airlines: [OpenFlights](https://openflights.org/data) (ODbL 1.0).
- Country borders: [Natural Earth](https://www.naturalearthdata.com) (public domain).
- Weather: [aviationweather.gov](https://aviationweather.gov) and the Iowa Environmental Mesonet.
- Basemap: © CARTO © OpenStreetMap contributors.
