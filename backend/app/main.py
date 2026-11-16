"""FastAPI application entry point."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.models.bootstrap import ensure_models

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Prepare model artifacts and the orchestrator before serving traffic."""
    settings = get_settings()
    configure_logging()
    logger.info(
        "Starting %s v%s (environment=%s)",
        settings.app_name, settings.app_version, settings.environment,
    )

    if settings.auto_train_on_startup:
        status = ensure_models()
        application.state.model_status = status.as_dict()
        if not status.ready:
            logger.error("Model bootstrap incomplete: %s", status.errors)
    else:
        application.state.model_status = {"skipped": "AUTO_TRAIN_ON_STARTUP is disabled"}

    from app.agents.llm import llm_info

    info = llm_info(settings)
    application.state.llm = info.as_dict()
    logger.info(
        "Orchestrator engine: %s (provider=%s model=%s)",
        "langgraph" if info.available else "deterministic", info.provider, info.model or "n/a",
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Build the configured application instance."""
    settings = get_settings()
    configure_logging()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Urban air-quality intelligence for Bengaluru: hyperlocal forecasting, source "
            "attribution, enforcement prioritisation, multilingual citizen advisories, and an "
            "LLM orchestrator that calls each agent as a tool."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_origin_regex=settings.origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )

    @application.middleware("http")
    async def access_log(request: Request, call_next):
        """Tag every request with an id and log its outcome and latency."""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed",
                extra={"request_id": request_id, "path": request.url.path, "method": request.method},
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers["x-request-id"] = request_id
        if request.url.path not in {"/health", "/"}:
            logger.info(
                "%s %s -> %s (%dms)",
                request.method, request.url.path, response.status_code, elapsed_ms,
                extra={"request_id": request_id, "duration_ms": elapsed_ms},
            )
        return response

    @application.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """Never leak a stack trace or internal message to a client."""
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "path": request.url.path},
        )

    application.include_router(api_router)

    @application.get("/", tags=["health"])
    def read_root() -> dict[str, str]:
        return {
            "message": f"{settings.app_name} is running",
            "version": settings.app_version,
            "docs": "/docs",
        }

    return application


app = create_app()
