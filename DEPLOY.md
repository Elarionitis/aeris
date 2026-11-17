# Deploying to Render

Two services from one repository: a Docker web service for the API and a
static site for the dashboard. Both fit Render's free tier — the API peaks at
about 269 MB against a 512 MB limit.

`render.yaml` in the repository root describes both. You can either use it as
a Blueprint or create the services by hand with the settings below.

---

## 1. Push the repository

Render deploys from GitHub, so the branch must be pushed first.

## 2. Create the API service

**New → Blueprint**, select this repository, and Render reads `render.yaml`.
Or **New → Web Service** with:

| Setting | Value |
| --- | --- |
| Runtime | Docker |
| Root directory | `backend` |
| Dockerfile path | `./Dockerfile` |
| Health check path | `/health` |
| Plan | Free |

Environment variables:

| Key | Value |
| --- | --- |
| `GROQ_API_KEY` | your key from console.groq.com |
| `ENVIRONMENT` | `production` |
| `LOG_FORMAT` | `json` |
| `ORCHESTRATOR_RATE_LIMIT` | `15` |
| `ORCHESTRATOR_CACHE_TTL_SECONDS` | `1800` |
| `CORS_ALLOW_ORIGINS` | *(set in step 4)* |

Note the service URL, e.g. `https://aeris-api.onrender.com`.

## 3. Create the dashboard

**New → Static Site**:

| Setting | Value |
| --- | --- |
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Publish directory | `dist` |

Environment variable `VITE_API_BASE` = the API URL from step 2. Vite inlines
this at build time, so changing it later requires a rebuild, not just a
restart.

Add a rewrite rule, Source `/*` → Destination `/index.html`, type Rewrite.
Without it, a refresh on any path 404s.

## 4. Connect them

Set `CORS_ALLOW_ORIGINS` on the API to the dashboard's exact URL, e.g.
`https://aeris-dashboard.onrender.com`, then redeploy the API.

This step is mandatory. `ENVIRONMENT=production` disables the permissive
localhost CORS regex used in development, so only the origins listed here can
call the API.

## 5. Verify

```bash
curl -s https://<your-api>.onrender.com/health | python3 -m json.tool
```

Check that:

- `"status": "ok"`
- `"models"` shows both as `ready`
- `"orchestrator"` shows `"provider": "groq"`

`"mode"` reads `"llm"` only after a question has succeeded; it is `"failing"`
with the provider's error if something is wrong. Ask a question in the
dashboard, then check `/health` again.

---

## The service URL may not be the name you chose

Render appends a suffix when a subdomain is taken, so `aeris-api` can deploy
as `aeris-api-oyuq.onrender.com`. The real URL is printed in the deploy log
as *"Available at your primary URL"*, and shown on the service page.

Take both URLs from there before setting `VITE_API_BASE` and
`CORS_ALLOW_ORIGINS`, rather than assuming them. Pointing the dashboard at a
URL that is not yours produces a request that hangs rather than fails, which
looks exactly like a CORS or networking fault.

## A provider package must be in the image

`requirements.txt` ships `langchain-core` but no vendor package, because the
choice of provider is yours. The Dockerfile therefore installs one through
the `LLM_PROVIDER_PACKAGE` build argument, defaulting to `langchain-groq`.

Without it the service starts, reports healthy, and answers every question
through deterministic routing. Build for a different provider with:

```bash
docker build --build-arg LLM_PROVIDER_PACKAGE=langchain-openai backend/
```

`/health` reports `"mode": "failing"` with `provider package ... is not
installed` when this is wrong.

## Ports

Render assigns the listening port through the `PORT` environment variable and
routes traffic only there. The Dockerfile reads it, defaulting to 8000 so
local runs and Compose are unchanged.

A container that hardcodes its port deploys and reports healthy while being
completely unreachable: TLS connects, then the request hangs until it times
out, because the edge is routing to a port nothing is listening on. If you
ever see that, check the port before suspecting CORS.

## What to expect on the free tier

**Cold starts.** The service sleeps after about 15 minutes idle. Waking it
takes roughly 30–50 seconds, including training the models. The first visitor
after a quiet period waits.

`.github/workflows/keep-warm.yml` handles this: it pings `/health` every ten
minutes from GitHub Actions, so the service never idles long enough to sleep
and nothing has to run on your own machine. Public repositories get unlimited
Actions minutes, so it is free.

It doubles as monitoring. The job fails, and GitHub emails you, if the service
stops responding or either model stops loading. A falling-back orchestrator is
reported as a warning rather than a failure, since that is usually a transient
provider outage.

Two caveats worth knowing:

- GitHub runs scheduled workflows on a best-effort basis and delays them under
  load, so a ping can arrive late. The cost is one visitor's cold start.
- GitHub disables scheduled workflows in repositories with no commits for 60
  days, and emails before doing so. Re-enable it from the Actions tab.

If you want tighter guarantees, point an external monitor such as UptimeRobot
at `/health` as well. The two do not conflict.

Alternatively, remove the cold start itself by baking the trained artifacts
into the image: drop `app/models/artifacts/*.pkl` from `.dockerignore` and
train before building, so startup only loads them.

**Rate limiting is per instance.** The limiter holds counts in memory, which
is accurate on the free tier's single worker. Running more than one instance
means each enforces its own budget; move the counter to Redis before scaling.

**The cache is per instance too**, and is lost on restart. That is fine for
its purpose, which is absorbing repeated demo questions.

## Budget guards

| Variable | Default | Effect |
| --- | --- | --- |
| `ORCHESTRATOR_RATE_LIMIT` | `20` | Questions allowed per window, per client IP |
| `ORCHESTRATOR_RATE_WINDOW_SECONDS` | `3600` | Length of that window |
| `ORCHESTRATOR_CACHE_TTL_SECONDS` | `900` | How long an answer is reused; `0` disables |
| `ORCHESTRATOR_CACHE_MAX_ENTRIES` | `256` | Cache size before least-recently-used eviction |

Only successful LLM answers are cached. Clients over the limit get a 429 with
`Retry-After`, and every response carries `X-RateLimit-Remaining`.

The dashboard's suggested prompts are identical for every visitor, so after
the first person asks one, the rest are served from cache at no provider cost.
