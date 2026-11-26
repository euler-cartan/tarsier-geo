"""Mounts the pre-built React frontend onto the FastAPI app (TAD §1, §4).

No separate frontend server, no network needed to load the UI: FastAPI serves
the static build directly. This checks two locations so the same code works
both for a published package (frontend copied in at build time) and for a
developer running from a source checkout.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


class _SPAStaticFiles(StaticFiles):
    """Falls back to index.html for any path that isn't a real file, so a
    hard navigation/refresh on a client-side route (e.g. /connections/{id}
    /overview) doesn't 404  -  React Router picks up from there instead.
    Found via live browser testing: refreshing a deep link broke outright.
    """

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # An unknown API path is a real 404, not the app shell with a 200.
            if exc.status_code == 404 and not path.replace("\\", "/").startswith("api/"):
                return await super().get_response("index.html", scope)
            raise

_PACKAGED_STATIC = Path(__file__).parent / "static"
_DEV_STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"

_PLACEHOLDER_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Tarsier</title></head>
  <body style="font-family: sans-serif; padding: 2rem;">
    <h1>Tarsier</h1>
    <p>Frontend build not found. Run <code>npm install &amp;&amp; npm run build</code>
    inside <code>frontend/</code>, or reinstall the packaged release.</p>
  </body>
</html>
"""


def _frontend_dir() -> Path | None:
    if (_PACKAGED_STATIC / "index.html").exists():
        return _PACKAGED_STATIC
    if (_DEV_STATIC / "index.html").exists():
        return _DEV_STATIC
    return None


def mount_frontend(app: FastAPI) -> None:
    static_dir = _frontend_dir()
    if static_dir is None:

        @app.get("/", response_class=HTMLResponse)
        def _placeholder() -> str:
            return _PLACEHOLDER_HTML

        return

    app.mount("/", _SPAStaticFiles(directory=str(static_dir), html=True), name="frontend")
