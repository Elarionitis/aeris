# Aeris on Google ADK

A small experiment: the same three analytical agents the LangGraph
orchestrator drives, exposed instead as tools to an agent built with Google's
[Agent Development Kit](https://google.github.io/adk-docs/).

The point is to see what changes when the orchestration framework changes.
The answer, mostly: not the agents. They are reached over the deployed REST
API here rather than in-process, which keeps this directory light and shows
that the analytical layer is not tied to any one framework.

```
  ADK LlmAgent                        LangGraph orchestrator
       │                                      │
       └──────────┬───────────────────────────┘
                  ▼  same four tools
   list_wards · forecast_ward_aqi
   attribute_ward_sources · rank_enforcement_priority
```

## Setup

Everything runs in its own virtualenv. ADK pulls a large dependency tree and
should not share one with the backend.

**1. Create the environment** (from the repository root):

```bash
cd experiments/adk && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

**2. Check your key**

The script reads `GROQ_API_KEY` from `backend/.env`, which is already set up
for the main service. Nothing else to configure.

**3. Run it**

```bash
cd experiments/adk && .venv/bin/python aeris_adk_agent.py "Why is BTM polluted and will it get worse?"
```

## What it looks like

```
API   : https://aeris-api-oyuq.onrender.com
Model : groq/openai/gpt-oss-120b
Q     : Which ward is worst right now and what is driving it?

  -> calling list_wards({})
  -> calling attribute_ward_sources({'ward': 'BTM'})

tools : ['list_wards', 'attribute_ward_sources']
A     : Worst ward now: BTM (AQI 168, Moderate band), driven mainly by industry.
```

Two hops, unscripted: it looked up the roster, found the worst ward, then
investigated it. The same question produces the same two-step plan through
the LangGraph orchestrator.

## Pointing it somewhere else

| Variable | Default | Purpose |
| --- | --- | --- |
| `AERIS_API_BASE` | the deployed API | Point at `http://localhost:8000` to use a local backend |
| `ADK_MODEL` | `groq/openai/gpt-oss-120b` | Any LiteLLM model string |

Against a local backend:

```bash
AERIS_API_BASE=http://localhost:8000 .venv/bin/python aeris_adk_agent.py "Give me a city overview"
```

With Gemini instead of Groq, ADK's native path, which needs no LiteLLM:

```bash
ADK_MODEL=gemini-2.5-flash GOOGLE_API_KEY=... .venv/bin/python aeris_adk_agent.py "..."
```

## Notes from building it

**Groq reasoning models need `reasoning_format="hidden"`.** The gpt-oss
models return a `reasoning_content` field, LiteLLM echoes it back on the next
turn, and Groq then rejects its own output with *"property 'reasoning_content'
is unsupported"*. The failure is confusing because the first tool call
succeeds and only the second step dies. Asking Groq to hide the reasoning
leaves nothing to echo. `_build_model` applies this automatically.

**Not every Groq model handles tools well.** `qwen/qwen3.8-27b` emitted
malformed tool calls that Groq rejected before they reached the agent. The
gpt-oss models were reliable.

**ADK reads the docstring as the tool interface.** It builds each schema from
the signature and the Google-style docstring, so the `Args:` descriptions are
genuinely prompt text, not documentation. That is the same lesson the
LangGraph tools taught, enforced more strictly.

## How it compares

| | LangGraph (`backend/app/agents`) | ADK (here) |
| --- | --- | --- |
| Graph | Explicit `StateGraph`, plan ⇄ act | Implicit, managed by the runner |
| Tools | `StructuredTool`, `Annotated` hints | Plain functions, docstring-derived |
| Control | You own the loop and its bound | The framework owns it |
| Sessions | None; stateless per request | Built in, with a session service |
| Reach | In-process calls | REST, as wired here |

ADK gets to a working agent with less wiring. LangGraph gives more say over
the loop itself, which is why the production path keeps it: the deterministic
fallback, the step bound and the tool-call trace all live in that loop.
