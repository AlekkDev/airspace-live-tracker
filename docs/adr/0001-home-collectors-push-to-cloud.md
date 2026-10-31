# ADR-0001 · Home collector pushes to the cloud

**Status:** accepted · 2026-10-27 · revised 2026-10-31

## Context
OpenSky blocks or throttles many data-centre IP ranges, so the server cannot poll it directly. We have no dedicated device yet, but we do have a Windows PC at home.

## Decision
One collector runs on a residential connection and **pushes** batches to an ingest API on the server. It polls on a 90 s grid, writes every response to a local spool before uploading, and retries until the server confirms. It also fetches OpenSky's daily flight lists, because those calls are subject to the same IP restriction.

On Windows the collector runs as a Task Scheduler task that starts at boot without a user signing in. A dedicated low-power Linux device replaces the PC once approved (open decision O7).

## Consequences
- The server never depends on reaching OpenSky from a data centre.
- Data already fetched is not lost when the server or the internet is down; it is only delayed, then caught up without disturbing the live map ([04](../04-pipelines.md#catch-up-after-an-outage-or-the-m0-backlog)).
- The map refreshes every 90 s. When the collector is down there is a gap. Gaps are measured and shown, never hidden.
- The home PC must stay on; electricity is a real cost (~€4–25/month, estimate).
- Alternatives considered:
  - Server polling OpenSky directly: blocked.
  - Server polling through a Tailscale exit node at home: still depends on home uptime and adds moving parts.
