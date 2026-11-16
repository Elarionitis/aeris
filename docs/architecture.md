# Architecture

## Overview

Four model agents read one shared ward-time dataset. Three of them are also
exposed as tools to an LLM orchestrator, so a single natural-language question
can draw on several at once.

```
                 ┌───────────────────────────────────────┐
  Dashboard ────►│  FastAPI                              │
  (React/Vite)   │   /wards /forecast /attribution       │
                 │   /enforcement /advisory /meta        │
                 │   /orchestrator/query  /orchestrator/tools
                 └───────┬───────────────────┬───────────┘
                         │                   │
                         │        ┌──────────▼───────────┐
                         │        │ LangGraph            │
                         │        │  plan ⇄ act loop     │
                         │        └──────────┬───────────┘
                         │                   │ in-process tool calls
          ┌──────────────┴───────────────────┴──────────────┐
          │                 model agents                    │
          │  forecasting · attribution · enforcement        │
          │  advisory (REST only)                           │
          └──────────────────────┬──────────────────────────┘
                                 │
                   ward-time master table (synthesised
                   baseline today, live feeds as they land)
                                 ▲
          ┌──────────────────────┴──────────────────────────┐
          │ ingestion: OpenAQ · OpenWeather/IMD · FIRMS ·   │
          │ traffic proxy · land use   (parquet cache)      │
          └─────────────────────────────────────────────────┘
```

## Layers

**`app/core`** — settings (pydantic-settings, `.env`-backed), logging, and the
CPCB band scale. The band scale lives here because the API and the dashboard
previously kept separate thresholds and disagreed about what AQI 168 was
called.

**`app/domain`** — the ward registry, the emission-source registry, and
vulnerability profiles, plus `resolve_ward_id`, which accepts an id, a display
name, or a near-miss. Everything upstream resolves ward identifiers through
it, so the API and the LLM cannot drift apart on naming.

**`app/ingestion`** — one client per upstream feed, each caching to parquet
under `data/raw/` and retrying with exponential backoff on 5xx and 429.

**`app/models`** — the four agents, plus `bootstrap.py`.

**`app/agents`** — the provider-agnostic LLM factory, the tool definitions,
and the LangGraph orchestrator.

**`app/api`** — routers and pydantic request/response schemas.

## Cold start

Trained artifacts are not committed, so `bootstrap.py` synthesises a
reproducible ward-hour master table and trains the forecasting and attribution
models from it during the FastAPI lifespan. The synthetic series carries a
diurnal and weekly cycle, an AR(1) residual so lag features are informative,
wind-driven dispersion, and source activity correlated with each ward's
land-use mix. A clean checkout serves real predictions about four seconds
after start, and each live feed replaces its synthetic counterpart as it
comes online.

## Orchestration

The graph is the standard tool-calling loop: `plan` is the LLM with the three
agent tools bound to it, `act` is a `ToolNode`, and the loop repeats until the
model answers without requesting another tool, bounded by
`ORCHESTRATOR_MAX_STEPS`.

Design decisions worth recording:

- **Tools call the model layer directly, not the REST API.** Orchestration adds
  no network hop and no second serialisation of the same data.
- **Tools summarise rather than dump.** The forecast tool returns the peak and
  its timing, a per-horizon summary, and a direction, not 72 raw points. This
  keeps the context small and the model's arithmetic honest.
- **Tools return errors as data.** An exception inside a tool call aborts the
  whole graph run, so every tool catches and returns `{"error": ...}`; the
  unknown-ward error includes the valid identifiers so the model can recover
  within the same run.
- **The provider is configurable.** Anthropic, OpenAI, and Gemini are all
  supported through the same factory; the advisory agent shares it.
- **There is always a path without an LLM.** With no key configured, a keyword
  router over the same tools answers instead. The response shape is identical
  and `engine` reports which ran, so the dashboard and the tests work offline.
  A provider error or an empty completion falls back the same way.

## Request flow

1. The dashboard loads `/meta` and `/wards`, then fetches forecast,
   attribution, advisory, and enforcement for the selected ward.
2. A question in the Ask Aeris panel goes to `/orchestrator/query` with the
   ward in focus as context.
3. The orchestrator plans, calls whichever agents it needs, and returns an
   answer plus the tool trace, which the panel renders as a chip per agent.

## Operational notes

- `/health` reports artifact readiness and the resolved orchestrator engine,
  and is what the container healthcheck polls.
- Every request is tagged with an `x-request-id` and logged with its latency.
  `LOG_FORMAT=json` emits one object per line.
- Unhandled exceptions are logged with a traceback and returned as a generic
  500; internal messages are never sent to a client.
- In production the permissive localhost CORS regex is dropped and only the
  configured origins are allowed.

## Known limitations

Ward boundaries are square placeholders pending BBMP geometry. The emission
source registry is illustrative. Attribution is modelled from activity proxies
rather than stack-level measurement. The baseline master table is synthetic
until the live feeds are keyed.
