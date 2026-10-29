# 07 · LLM layer

Provider: Anthropic Claude API via the official Python SDK, client in `services/llm`.
- Model: **Claude Haiku 5.5** (`claude-haiku-5-5`) for both features. Model ids live in config (`LLM_MODEL_BRIEFING`, `LLM_MODEL_CHAT`), not code.
- Switching the chat to Claude Sonnet 5.5 (`claude-sonnet-5-5`) is allowed only if the CI eval with Haiku stays below 80%, and only after the daily chat cap is re-sized (Sonnet costs about 20× more per question).
- Prompts are versioned files in `services/llm/prompts/` (e.g. `briefing_v3.md`); the version is stored with every output.
- Spend control: per-IP and global chat caps ([05](05-api-contract.md#post-chat)) and an Anthropic console spend limit of $40/month.

## 1 · Airspace briefing

**Cadence:** every 30 min (`llm_briefing`, window = the 30 min that just ended).

**Principle:** the model writes prose; it never invents numbers. All facts are computed in SQL first:

```json
{
  "window": "2026-11-03T14:00Z/14:30Z",
  "aircraft_now": 9412, "vs_typical_pct": -4.1,
  "top_anomalies": [{"area":"near Munich (EDDM), Germany","direction":"high","z":3.8,"persistent":true}],
  "events": [{"kind":"go_around","airport":"LOWW","callsign":"AUA478","ts":"14:12Z"}],
  "weather": {"LOWW":"IFR, wind 300° 11 m/s gusting 18 m/s", "LHBP":"VFR", "LZIB":"MVFR"},
  "arrivals_next_hour": {"LOWW": 31, "LZIB": 3, "LHBP": 14},
  "data_quality": "pass"
}
```

- `vs_typical_pct`: airborne aircraft now vs the median for this hour of week over the last 28 days.
- `top_anomalies`: up to 3 clusters from the window's `anomaly_start` events, largest `|z|` first. Place names: nearest `large_airport` to the anchor cell centre, plus the country from `ref.h3_r4_country`.
- `arrivals_next_hour`: flights whose latest `eta_p50` falls in the next 60 min.

**Prompt rules:**
- 120–200 words of Markdown: one headline sentence, then bullets for Central Europe, unusual traffic, notable events, and weather at the three airports.
- Use only numbers from the facts JSON. Do not compute new ones.
- State weather as conditions; never claim that weather caused traffic changes or events.
- A `low` anomaly is described as "lower than usual (possibly a receiver coverage gap)".

**Number check** (stored as `llm.briefings.number_check`):
1. Extract every number from the output, ignoring tokens that contain letters (e.g. `AUA478`, `FL100`) and times in `HH:MM` or `HH:MMZ` form that appear in the facts.
2. Normalise: remove thousands separators, `%` and `+`.
3. Each number must equal a number from the facts JSON, either exactly or after rounding that fact to 0 or 1 decimal places.
4. Any unmatched number → `fail`. A failed briefing is stored but never served; the previous passing one stays visible.

**Stored in:** `llm.briefings`, with the facts JSON, so every claim can be checked afterwards.

## 2 · Chat: text-to-SQL

```mermaid
sequenceDiagram
  participant U as Visitor
  participant A as public-api
  participant C as Claude
  participant D as Postgres (llm_readonly)
  U->>A: POST /chat {question}
  A->>A: limits: length, per-IP, daily cap
  A->>C: system prompt + view catalogue (cached) + question, tool run_sql
  C->>A: tool_use run_sql(sql)
  A->>A: guard (below)
  A->>D: BEGIN READ ONLY; SET LOCAL statement_timeout = '5s'; wrapped query; COMMIT
  D-->>A: rows
  A->>C: tool_result (rows, max 50 shown to the model)
  C-->>A: answer (Markdown)
  A-->>U: answer_md + sql + rows (max 200)
```

### Guardrails

1. **Role:** `llm_readonly` can only `SELECT` from `llm.v_*`; `default_transaction_read_only = on`.
2. **Per transaction:** every query runs in its own `BEGIN READ ONLY` transaction that starts with `SET LOCAL statement_timeout = '5s'`, so nothing a query does can outlive it.
3. **Parser check (sqlglot, Postgres dialect):**
   - exactly one statement, and it is a `SELECT` (CTEs allowed);
   - every relation is an `llm.v_*` view;
   - every function call is on the allow-list: `count, sum, avg, min, max, round, abs, ceil, floor, coalesce, nullif, greatest, least, lower, upper, length, trim, concat, date_trunc, date_part, extract, now, to_char, percentile_cont, row_number, rank, dense_rank, lag, lead`. Anything else (including `set_config`, `pg_sleep`, `dblink`, file and admin functions) is rejected;
   - no `INTO`, no locking clauses (`FOR UPDATE` etc.).
4. **Row cap:** the query is wrapped as `SELECT * FROM (<query>) AS q LIMIT 200`.
5. **Loop cap:** at most 3 tool calls per question.
6. **Transparency:** the generated SQL is always shown in the UI.

A rejected query is returned to the model as a tool error with the reason, counting towards the 3 calls.

**Prompt:** the system prompt contains `db/llm_views.md`: every view, column, unit, example values, and 10 example question → SQL pairs. It is marked for prompt caching.

**What the chat can answer:** live traffic by country (`over_country`), airline (`airline_name`), airport arrivals and ETAs, events, weather, and hourly traffic history. Questions outside the views get a plain "I can't answer that from this data".

## 3 · Evaluation (CI)

- `services/llm/eval/golden.yaml`: 30+ questions, each with a reference SQL or an expected-answer check. Examples:
  - "How many aircraft are airborne over Austria right now?"
  - "Busiest hour at LHBP yesterday?"
  - "Any emergency squawks today?"
- `llm-eval.yml` runs them against the fixture database (`db/seeds/fixture/`) and scores **execution accuracy** (the result set matches the reference SQL's result). The build fails below 80%.
- Runs when any of these change: `services/llm/**`, `db/llm_views.md`, `db/migrations/**`, `db/seeds/fixture/**`.
- Briefing eval: the number check above runs on 10 fixture facts files; any `fail` fails the build.
- Results are uploaded as a GitHub Actions artifact (`llm-eval.json`) and summarised in the job summary. CI does not write to MLflow.
