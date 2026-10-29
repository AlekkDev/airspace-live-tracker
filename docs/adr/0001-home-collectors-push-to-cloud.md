# ADR-0001 · Home collectors push to the cloud

**Status:** accepted · 2026-10-27 · revised 2026-10-29

## Context
OpenSky blocks or throttles many data-centre IP ranges, and each account gets 4,000 `/states/*` credits a day, which is one global query about every 90 s. We have no dedicated device yet, but each of us has a Windows PC at home.

## Decision
Collectors run on residential connections and **push** batches to an ingest API on the server. Each collector writes every response to a local spool before uploading, and retries until the server confirms. Two collectors with separate OpenSky accounts run on the same 90 s grid, offset by 45 s. The collectors also fetch OpenSky's daily flight lists, because those calls are subject to the same IP restriction.

On Windows the collector runs as a Task Scheduler task that starts at boot without a user signing in. A dedicated low-power Linux device replaces the PCs once approved (open decision O7).

## Consequences
- The server never depends on reaching OpenSky from a data centre.
- No data is lost when the server or the internet is down; it is only delayed, then caught up without disturbing the live map ([04](../04-pipelines.md#catch-up-after-an-outage-or-the-m0-backlog)).
- With both collectors running, refresh is ~45 s; with one, 90 s; with none, there is a gap. Gaps are measured and shown, never hidden.
- Home PCs must stay on; electricity is a real cost (~€8–50/month for two PCs, estimate).
- Using two personal accounts for one project must be confirmed against OpenSky's terms in M0. If not allowed, one collector polls and refresh is 90 s.
- Alternatives considered:
  - Server polling OpenSky directly: blocked.
  - Server polling through a Tailscale exit node at home: still depends on home uptime and adds moving parts.
