FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so application edits do not invalidate the wheel cache.
# A provider package is what makes the orchestrator able to call an LLM at
# all; without one the service starts fine and silently falls back to
# deterministic routing. Groq is the documented default; override to build an
# image for a different provider, or pass "" for a deterministic-only image.
ARG LLM_PROVIDER_PACKAGE="langchain-groq>=0.2.0"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ -n "$LLM_PROVIDER_PACKAGE" ]; then pip install --no-cache-dir "$LLM_PROVIDER_PACKAGE"; fi

COPY app ./app

# Run unprivileged; the app only needs to write its model artifacts.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/app/models/artifacts \
    && chown -R appuser:appuser /app
USER appuser

# Managed hosts (Render, Fly, Cloud Run) assign the listening port through
# PORT and route only there. Default to 8000 so local runs are unchanged.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request,sys; port=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4).status == 200 else 1)"

# Shell form so ${PORT} expands; exec so uvicorn receives signals as PID 1.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
