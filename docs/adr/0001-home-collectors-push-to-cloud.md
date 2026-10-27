# ADR-0001 · Home collectors push to the cloud

**Status:** accepted · 2026-10-27

## Context
OpenSky blocks or throttles many data-centre IP ranges, and registered accounts are limited to roughly one global query per 90 s. We have no Raspberry Pi yet, but each of us has a Windows PC at home.

## Decision
Collectors run on residential connections (our PCs now, a Pi later) and **push** batches to an ingest API on the VPS. Each collector writes every response to a local spool before uploading, and retries until the server confirms. Two collectors with separate OpenSky accounts run on the same 90 s grid, offset by 45 s.

## Consequences
- The server never depends on OpenSky reachability from the data centre.
- No data is lost when the server or internet is down; it is only delayed.
- When both PCs run, refresh is ~45 s. With one, it is 90 s. With none, there is a gap. Gaps are measured and shown, never hidden.
- Home PCs must stay on. Docker Desktop autostarts, and sleep is disabled while plugged in.
- Alternatives considered:
  - VPS polling OpenSky directly: blocked.
  - VPS polling through a Tailscale exit node at home: still depends on home uptime, adds moving parts. Kept as a fallback.
