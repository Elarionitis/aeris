# Aeris 🌍

> **AI-powered air-quality intelligence — forecasting pollution, identifying its sources, prioritising inspections, and delivering actionable citizen advisories, coordinated by an LLM agent.**

Aeris is a full-stack **air-quality decision-support platform**. Instead of only showing the current AQI, it answers the questions that follow from it:

- 🔮 What will the AQI look like over the next 1–72 hours?
- 🔎 What is actually causing the pollution here?
- 🚨 Which wards should inspection teams visit first?
- 🧑‍🤝‍🧑 What should residents do right now, in their own language?
- 💬 …and now, all of the above from a single question in plain English.

**Core workflow:**

```text
Forecast → Explain → Prioritize → Act
```

---

## ✨ What's new: multi-agent orchestration

Four specialist model agents share one ward-time dataset. Three of them are exposed as **tools to an LLM orchestrator built on LangGraph**, so one natural-language question can draw on several agents at once.

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

The orchestrator decides which agents to call. Asked *"which ward is worst and what is driving it?"* with no ward in context, it looks up the ward registry, finds the worst, then runs attribution on it — two hops, unscripted.

A fourth agent writes multilingual citizen advisories and is served directly at `/advisory/{ward_id}`.

---

## 🧩 Features

### 🔮 AQI Forecasting
- Ward-level forecasting up to 72 hours
- Lagged AQI, rolling means, weather, source-activity and cyclical calendar features
- Gradient-boosted multi-horizon regression, rolled forward recursively
- Prediction intervals that widen with the square root of the horizon
- Scored against a persistence baseline

### 🔎 Pollution Attribution
- Estimates contributions from traffic, construction, industrial activity and thermal anomalies
- **Non-Negative Least Squares**, so no source can "clean" the air and the coefficients stay interpretable
- Shares always sum to 100, with the fitted intercept reported as background
- Confidence score (R²) on every response

### 🚨 Enforcement Prioritisation
- Severity × controllable emission share × registered sources within 1 km × persistence in band
- A ward stuck in its band for five days outranks a first-day peer
- Returns the corroborating source coordinates with each recommendation

### 🧑‍🤝‍🧑 Citizen Advisory
- English, Kannada, Tamil and Hindi
- Vulnerability-weighted by school/hospital density and elderly share
- LLM-written when a provider is configured, behind a filter that rejects anything resembling medical dosing; otherwise a reviewed template
- Cached on disk, written atomically

### 💬 Ask Aeris (orchestrator)
- One question, routed across the agents
- Every answer shows a chip per agent consulted, so the reasoning path is visible
- Falls back to deterministic routing when no LLM is configured

### 🗺️ Interactive Dashboard
- Ward map, 72-hour forecast with confidence band, attribution breakdown, enforcement queue, advisory panel
- Band scale and languages served by the API so the UI can never disagree with it
- Responsive, keyboard-accessible, with per-panel error recovery

---

## 🚀 Getting Started

### Prerequisites

- Python **3.11+**
- Node **18+**

### Clone

```bash
git clone https://github.com/Elarionitis/aeris.git && cd aeris
```

### Backend

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend && npm install && npm run dev
```

Dashboard at **http://localhost:5173**, API docs at **http://localhost:8000/docs**.

**No configuration is required to start.** On first run the service synthesises a reproducible ward-hour history, trains the forecasting and attribution models from it (~4 seconds), and serves real predictions. Without an LLM key the orchestrator answers through deterministic tool routing.

### Docker

```bash
docker compose up --build
```

Production-style stack (built frontend behind nginx, JSON logs):

```bash
docker compose -f docker-compose.prod.yml up --build
```

---

## 🔑 Enabling the LLM orchestrator

The orchestrator needs a model that supports **tool calling**. With `LLM_PROVIDER=auto` the first configured provider in this order is used, so one key is enough even if others are present.

| Provider | `LLM_PROVIDER` | Package | Notes |
| --- | --- | --- | --- |
| **Groq** | `groq` | `langchain-groq` | **Recommended.** Free tier, fast, reliable tool calling |
| Anthropic | `anthropic` | `langchain-anthropic` | Paid |
| OpenAI | `openai` | `langchain-openai` | Paid |
| Hugging Face / OpenRouter / Cerebras / Together | `openai_compatible` | `langchain-openai` | Set `LLM_BASE_URL` + `LLM_MODEL` |
| Google Gemini | `google` | `langchain-google-genai` | Free tier often 503s under load |

Quickest route — Groq:

```bash
pip install langchain-groq
```

Then add to `backend/.env`:

```
GROQ_API_KEY=gsk_...
```

Any OpenAI-compatible endpoint instead:

```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://router.huggingface.co/v1
LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct
LLM_API_KEY=hf_...
```

`LLM_MODEL` is required there, because the model id belongs to whichever endpoint you point at.

### Confirming it actually works

A provider that is *configured* is not necessarily a provider that *answers*. A retired model id or an overloaded endpoint fails every call while the orchestrator keeps working through its fallback — so `/health` reports what real calls did, not what is configured:

```bash
curl -s localhost:8000/health | python3 -m json.tool
```

`"mode": "llm"` means a call has succeeded. `"mode": "failing"` carries the provider's own error and the time of the last success.

---

## ⚙️ Configuration

Copy `backend/.env.example` to `backend/.env`. Every value is optional.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` drops the permissive localhost CORS regex |
| `CORS_ALLOW_ORIGINS` | localhost:5173 | Comma-separated exact origins |
| `LOG_FORMAT` | `text` | `json` for one object per line |
| `LLM_PROVIDER` | `auto` | `auto`, `groq`, `anthropic`, `openai`, `openai_compatible`, `google`, `none` |
| `LLM_MODEL` | per provider | Override the default model id |
| `ORCHESTRATOR_MAX_STEPS` | `8` | Bound on the plan ⇄ act loop |
| `AUTO_TRAIN_ON_STARTUP` | `true` | Train missing model artifacts at startup |
| `ENABLE_PROPHET_BASELINE` | `false` | Per-ward Prophet baseline; slow, not used for serving |

---

## 🔌 API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Artifact readiness and real orchestrator state |
| `GET /meta` | Band scale, languages, limits |
| `GET /wards` | Ward registry with current AQI, band and map geometry |
| `GET /forecast/{ward_id}?hours=` | Forecast from the service's own ward history |
| `POST /forecast/{ward_id}` | Forecast from caller-supplied feature history |
| `GET /attribution/{ward_id}` | Source split, with optional per-feature overrides |
| `GET /enforcement/priority-queue?limit=` | Wards ranked for inspection |
| `GET /advisory/{ward_id}?lang=` | Advisory in `en`, `kn`, `ta` or `hi` |
| `POST /orchestrator/query` | Ask across the agents |
| `GET /orchestrator/tools` | Agent tool catalogue |

Example:

```bash
curl -s localhost:8000/orchestrator/query -H 'content-type: application/json' \
  -d '{"question": "Why is BTM polluted and will it get worse?", "ward_id": "BTM"}'
```

```json
{
  "answer": "BTM's pollution is driven mainly by industrial sources (~61% of the modelled share)…",
  "engine": "langgraph",
  "llm": { "provider": "groq", "model": "openai/gpt-oss-120b", "mode": "llm" },
  "trace": [
    { "tool": "attribute_ward_sources", "agent": "attribution", "ok": true },
    { "tool": "forecast_ward_aqi", "agent": "forecasting", "ok": true }
  ],
  "elapsed_ms": 2141
}
```

### Agent tools

| Tool | Agent | Answers |
| --- | --- | --- |
| `forecast_ward_aqi` | Forecasting | What will the air be like in the next 1–72 hours? |
| `attribute_ward_sources` | Attribution | What is causing this ward's pollution? |
| `rank_enforcement_priority` | Enforcement | Where should inspection teams go first? |
| `list_wards` | Registry | Which wards exist, and what are they reading now? |

Tools call the model layer in-process, so orchestration adds no network hop. Each returns `{"error": ...}` instead of raising, because an exception inside a tool call aborts the graph run, and each summarises its agent's output so the model never has to read 72 raw forecast points.

---

## 🛠️ Tech Stack

**Backend** — FastAPI, pydantic-settings, pandas, scikit-learn, SciPy, LangGraph, LangChain
**Frontend** — React 18, Vite, Tailwind CSS, Recharts, React-Leaflet
**Infra** — Docker, nginx, pytest

---

## 📁 Project Structure

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

---

## 🧪 Testing

```bash
cd backend && python -m pytest
```

84 tests covering API contracts against the real application, model quality against a persistence baseline, the agent tools, settings resolution, and the orchestrator graph. The graph is exercised with a scripted fake chat model, and an autouse fixture stubs the LLM off, so **the suite never makes a billable network call** even with a key in `.env`.

---

## 📊 Model Evaluation

`evaluate_forecast` scores every horizon against a persistence baseline — "AQI stays where it is" — which is the bar any short-horizon air-quality model has to clear to be worth deploying. Attribution reports R² on each response. See `docs/evaluation_report.md`.

AQI bands follow the **CPCB National Air Quality Index** and are defined once in `backend/app/core/aqi.py`, which both the API and the dashboard read.

---

## ⚠️ Responsible Use

This is **decision support, not an enforcement system of record**.

- Ward boundaries are square placeholders pending BBMP geometry
- The emission source registry is illustrative
- Attribution is modelled from activity proxies, not stack-level measurement
- **The baseline ward history is synthetic.** Ingestion clients for OpenAQ, OpenWeather and NASA FIRMS are written and tested, but are not yet wired into the serving path
- Advisory translations should be reviewed by a native speaker before dispatch
- Advisories deliberately avoid any medical specificity

---

## 🗺️ Roadmap

- [ ] Wire the ingestion clients into a scheduled job building the real master table
- [ ] Real BBMP ward boundaries
- [ ] Rate limiting and caching on the orchestrator endpoint before public deployment
- [ ] Retrain on live data and re-evaluate against the persistence baseline
- [ ] Advisory agent as a fourth orchestrator tool

---

## 🎯 Vision

Air-quality dashboards tell you the air is bad. Aeris is built to tell you **why**, **what happens next**, **who should act**, and **what to do in the meantime** — and to let you ask for all of it in one sentence.
