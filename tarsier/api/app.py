"""FastAPI app factory. Serves the API and the bundled frontend (TAD §1, §4)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from tarsier import __version__
from tarsier.api.snapshots import router as snapshots_router
from tarsier.api.local_guard import local_guard
from tarsier.api.navigation import router as navigation_router
from tarsier.api.about import router as about_router
from tarsier.api.ai import router as ai_router
from tarsier.api.alerts import router as alerts_router
from tarsier.api.automations import router as automations_router
from tarsier.api.changes import router as changes_router
from tarsier.api.connections import router as connections_router
from tarsier.api.graph import router as graph_router
from tarsier.api.flowchart import cross_router as flowchart_cross_router
from tarsier.api.flowchart import router as flowchart_router
from tarsier.api.overview import router as overview_router
from tarsier.api.quality import router as quality_router
from tarsier.api.settings import router as settings_router
from tarsier.changes.scheduler import start_scheduler, stop_scheduler
from tarsier.connectors.base import ConnectorError
from tarsier.web.serve import mount_frontend


_log = logging.getLogger("tarsier.api")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        from tarsier.storage.webhook_vault import migrate_legacy

        migrate_legacy()
    except Exception:
        _log.warning("Could not move saved webhook URLs into the credential store.", exc_info=True)
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    # The auto-generated /docs and /redoc pages load their scripts from a public
    # CDN, which would make the user's browser phone out (TAD §9: no outbound
    # traffic except a configured AI). Tarsier ships its own UI, so they are off.
    app = FastAPI(title="Tarsier", version=__version__, lifespan=_lifespan, docs_url=None, redoc_url=None)

    app.middleware("http")(local_guard)

    # Safety net under every route. A source that is down, a table the user may
    # not read, or a bug must reach the UI as a readable JSON message  -  never
    # as a bare "Internal Server Error" page, and never as a driver traceback.
    @app.exception_handler(ConnectorError)
    async def _connector_error(_request: Request, exc: ConnectorError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(_request: Request, exc: RequestValidationError):
        # FastAPI's default `detail` is a list of objects, which the UI printed
        # as "[object Object]". Say which field is wrong, in one sentence.
        problems = []
        for error in exc.errors()[:3]:
            field = ".".join(str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path"))
            problems.append(f"{field}: {error.get('msg', 'invalid value')}" if field else error.get("msg", "invalid value"))
        return JSONResponse({"detail": "Check the values entered. " + "; ".join(problems)}, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception):
        _log.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            {"detail": "Tarsier hit an unexpected problem with this request. Details are in the server log."},
            status_code=500,
        )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.include_router(connections_router)
    app.include_router(overview_router)
    app.include_router(flowchart_router)
    app.include_router(flowchart_cross_router)
    app.include_router(graph_router)
    app.include_router(quality_router)
    app.include_router(changes_router)
    app.include_router(alerts_router)
    app.include_router(automations_router)
    app.include_router(ai_router)
    app.include_router(settings_router)
    app.include_router(about_router)
    app.include_router(navigation_router)
    app.include_router(snapshots_router)

    mount_frontend(app)
    return app
