# AQI Intelligence

Urban air-quality intelligence for Bengaluru. Four model agents share one
ward-time dataset, and an LLM orchestrator built on **LangGraph** calls the
analytical ones as tools to answer questions in plain language.

```
                         ┌──────────────────────────────┐
   "Why is BTM bad and   │   LangGraph orchestrator     │
    will it get worse?"  │   plan ⇄ act loop, tools     │
            ───────────► │   bound to the LLM           │
                         └───────┬──────────────────────┘
                                 │ tool calls
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
   ┌─────────────┐      ┌────────────────┐      ┌───────────────┐
   │ Forecasting │      │  Attribution   │      │  Enforcement  │
   │ 1–72h AQI   │      │  NNLS source   │      │  inspection   │
   │ + intervals │      │  split         │      │  ranking      │
   └──────┬──────┘      └───────┬────────┘      └───────┬───────┘
          └─────────────────────┼───────────────────────┘
                                ▼
                     shared ward-time master table
```

A fourth agent writes multilingual citizen advisories and is served directly
at `/advisory/{ward_id}` rather than as an orchestrator tool.

## Quick start

```bash
git clone <this-repo> && cd aeris
```

Backend (Python 3.11+):

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```bash
cd frontend && npm install && npm run dev
```

The dashboard is at http://localhost:5173 and the API docs at
http://localhost:8000/docs.

No configuration is required. On first start the service synthesises a
reproducible ward-hour history, trains the forecasting and attribution models
from it (about four seconds), and serves real predictions. With no LLM key the
orchestrator answers through deterministic tool routing instead of an LLM.

### Docker

```bash
docker compose up --build
```

For a production-style stack (built frontend behind nginx, JSON logs):

```bash
docker compose -f docker-compose.prod.yml up --build
```

## Configuration

Copy `backend/.env.example` to `backend/.env` and fill in what you need; every
value is optional. The settings that matter most:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` drops the permissive localhost CORS regex |
| `CORS_ALLOW_ORIGINS` | localhost:5173 | Comma-separated exact origins |
| `LOG_FORMAT` | `text` | `json` for one object per line |
| `LLM_PROVIDER` | `auto` | `auto`, `groq`, `anthropic`, `openai`, `openai_compatible`, `google`, `none` |
| `GROQ_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | empty | Any one enables LangGraph planning |
| `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL` | empty | Any OpenAI-compatible endpoint |
| `AUTO_TRAIN_ON_STARTUP` | `true` | Train missing model artifacts at startup |
| `ENABLE_PROPHET_BASELINE` | `false` | Per-ward Prophet baseline; slow, not used for serving |

### Choosing a provider

The orchestrator needs a model that supports **tool calling**. Any of these
work; install the matching package and set the key. With `LLM_PROVIDER=auto`
the first configured provider in this table's order is used, so a Groq key is
enough on its own even if other keys are present.

| Provider | `LLM_PROVIDER` | Package | Notes |
| --- | --- | --- | --- |
| Groq | `groq` | `langchain-groq` | Free tier, fast, good tool calling |
| Hugging Face | `openai_compatible` | `langchain-openai` | Set `LLM_BASE_URL` + `LLM_MODEL` |
| OpenRouter | `openai_compatible` | `langchain-openai` | Set `LLM_BASE_URL` + `LLM_MODEL` |
| OpenAI | `openai` | `langchain-openai` | Paid |
| Anthropic | `anthropic` | `langchain-anthropic` | Paid |
| Google Gemini | `google` | `langchain-google-genai` | Free tier often 503s under load; set explicitly |

Groq, the quickest route to a working orchestrator:

```bash
pip install langchain-groq
```

then put `GROQ_API_KEY=...` in `backend/.env`.

Hugging Face, or any other OpenAI-compatible endpoint:

```bash
pip install langchain-openai
```

```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://router.huggingface.co/v1
LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct
LLM_API_KEY=hf_...
```

`LLM_MODEL` is required here, because the model id belongs to whichever
endpoint you pointed at. `app/core/config.py` lists ready-made base URLs for
Hugging Face, OpenRouter, Cerebras and Together.

### Checking it actually works

A provider that is configured is not necessarily a provider that answers. A
retired model id or an overloaded endpoint fails every call while the
orchestrator keeps working through its deterministic fallback. `/health`
reports what real calls did:

```bash
curl -s localhost:8000/health | python3 -m json.tool
```

`"mode": "llm"` means a call has succeeded. `"mode": "failing"` includes the
provider's own error and the time of the last success.

## The orchestrator

`POST /orchestrator/query`

```bash
curl -s localhost:8000/orchestrator/query -H 'content-type: application/json' \
  -d '{"question": "Why is BTM polluted and will it get worse?", "ward_id": "BTM"}'
```

The response carries the answer, the engine that produced it, and a trace of
every agent that was consulted:

```json
{
  "answer": "BTM is at AQI 168 (Moderate), and the attribution agent puts 57% …",
  "engine": "langgraph",
  "llm": {"provider": "anthropic", "mode": "llm"},
  "trace": [
    {"tool": "attribute_ward_sources", "agent": "attribution", "ok": true},
    {"tool": "forecast_ward_aqi", "agent": "forecasting", "ok": true}
  ],
  "elapsed_ms": 2140
}
```

### Agent tools

`GET /orchestrator/tools` returns the live schemas.

| Tool | Agent | Answers |
| --- | --- | --- |
| `forecast_ward_aqi` | Forecasting | What will the air be like in the next 1–72 hours? |
| `attribute_ward_sources` | Attribution | What is causing this ward's pollution? |
| `rank_enforcement_priority` | Enforcement | Where should inspection teams go first? |
| `list_wards` | Registry | Which wards exist, and what are they reading now? |

Tools call the model layer in-process, so orchestration adds no network hop.
Each returns `{"error": ...}` instead of raising, because an exception inside a
tool call aborts the graph run, and each summarises its agent's output so the
model never has to read 72 raw forecast points.

### How the graph runs

```
START → plan → (tool calls requested?) → act → plan → … → END
```

`plan` is the LLM with the tools bound; `act` is a LangGraph `ToolNode`. The
loop is bounded by `ORCHESTRATOR_MAX_STEPS`.

### Without an LLM key

The graph is bypassed for a deterministic keyword router over the same tools.
The response shape is identical and `engine` reports which path ran, so the
dashboard, the test suite, and an offline demo all work unchanged. A provider
error or an empty completion falls back the same way.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Artifact readiness and resolved orchestrator engine |
| `GET /meta` | Band scale, languages, limits — the dashboard reads these |
| `GET /wards` | Ward registry with current AQI, band, and map geometry |
| `GET /forecast/{ward_id}?hours=` | Forecast from the service's own ward history |
| `POST /forecast/{ward_id}` | Forecast from caller-supplied feature history |
| `GET /attribution/{ward_id}` | Source split, with optional per-feature overrides |
| `GET /enforcement/priority-queue?limit=` | Wards ranked for inspection |
| `GET /advisory/{ward_id}?lang=` | Citizen advisory in `en`, `kn`, `ta`, or `hi` |
| `POST /orchestrator/query` | Ask across the agents |
| `GET /orchestrator/tools` | Agent tool catalogue |

## The models

**Forecasting.** Gradient-boosted multi-horizon regression over lagged AQI,
rolling means, weather, source-activity features, and cyclical hour and
weekday terms. Serving rolls the 1-hour head forward recursively, widening the
interval with the square root of the horizon. Scored against a persistence
baseline by `evaluate_forecast`.

**Attribution.** Non-negative least squares of AQI on traffic, construction,
industrial, and thermal-anomaly signals. Non-negativity is what keeps the
coefficients interpretable: no source is allowed to clean the air. Shares sum
to 100, with the fitted intercept reported as background under "other".

**Enforcement.** Severity × controllable emission share × registered sources
within 1 km × how long the ward has persisted in its band.

**Citizen advisory.** Vulnerability-weighted guidance in four languages. An
LLM writes it when one is configured, behind a filter that rejects anything
reading like medical dosing; otherwise a reviewed template is used. Results
are cached on disk.

AQI bands follow the CPCB National Air Quality Index and are defined once in
`backend/app/core/aqi.py`, which both the API and the dashboard read.

## Data sources

OpenAQ (measurements), OpenWeather or IMD (meteorology), NASA FIRMS (thermal
anomalies), and a land-use loader for source proxies. Clients cache to parquet
under `data/raw/` and retry with exponential backoff. Until live keys are
configured the service runs on its synthesised baseline history.

## Tests

```bash
cd backend && python -m pytest
```

78 tests covering API contracts against the real application, model quality
against a persistence baseline, the agent tools, and the orchestrator graph.
The graph is exercised with a scripted fake chat model, so the tool loop and
both fallback paths are tested without an API key or a network call.

## Layout

```
backend/app/
  core/        settings, logging, the CPCB band scale
  domain/      ward registry, emission sources, vulnerability profiles
  ingestion/   OpenAQ, weather, FIRMS, traffic, land-use clients
  models/      forecasting, attribution, enforcement, advisory, bootstrap
  agents/      LLM factory, agent tools, LangGraph orchestrator
  api/         routes, schemas, orchestrator endpoints
frontend/src/
  lib/         API client, band helpers, data-loading hook
  components/  map, charts, queue, advisory, orchestrator chat
docs/          architecture notes, evaluation report, deck outline
```

## Caveats

Ward boundaries are square placeholders pending BBMP geometry, the emission
source registry is illustrative, and attribution is modelled from activity
proxies rather than stack-level measurement. Advisory translations should be
reviewed by a native speaker before dispatch. This is decision support, not an
enforcement system of record.
