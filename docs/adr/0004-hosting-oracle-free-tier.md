# ADR-0004 · Host the server on Oracle Cloud Always Free

**Status:** accepted · 2026-10-29

## Context
The first plan was a Hetzner CX33 (4 vCPU, 8 GB, 80 GB, €8.99/month). In October 2026 it is listed as currently not available; the closest orderable plan costs €35.99/month. Our estimated storage (~50–60 GB raw at 90 days plus everything else) also no longer fits comfortably on 80 GB. Azure's $100 student credit covers only about 6 weeks of an 8 GB VM.

## Decision
Run the server on Oracle Cloud Infrastructure Always Free in `eu-frankfurt-1`: one `VM.Standard.A1.Flex` with 2 OCPU (ARM), 12 GB RAM and 200 GB block storage, Ubuntu 24.04. Upgrade the tenancy to Pay As You Go with a €1 budget alert. If no A1 capacity is obtained by the end of week 1, use a Contabo Cloud VPS 10 (~€5/month, amd64) instead.

## Consequences
- €0 hosting with more RAM and disk than the original plan.
- Every image is built for arm64 and amd64, so switching to the fallback changes nothing but the host.
- 2 cores are enough for a mostly idle workload with short bursts; heavy jobs (training at 03:00, backup at 04:00) are scheduled apart.
- Ingress is restricted to Cloudflare's IP ranges and SSH is only reachable over Tailscale ([01](../01-architecture.md#networking-and-security)).
- Alternatives considered:
  - Hetzner CPX32 (€35.99): works but costs more than every other option.
  - Azure B2as_v2 (~$63/month after credit): over budget.
  - A home PC behind Cloudflare Tunnel: €0, but home uptime would decide everything, which is a weak story for a cloud course.
