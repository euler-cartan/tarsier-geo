"""Keep the unauthenticated desktop API accessible from its own local UI only.

Tarsier has no login: it binds to 127.0.0.1 and trusts whoever sits at this
machine. That makes the browser the attack surface  -  a web page open in
another tab must not be able to drive the API. Three independent checks:

1. Host header must be a loopback name (defeats DNS rebinding).
2. An Origin header, when sent, must be Tarsier's own origin (defeats
   cross-site POST/PUT/DELETE).
3. Sec-Fetch-Site, sent by every current browser, must not say the request
   came from another site (defeats cross-site GETs  -  image tags, links  -
   which carry no Origin header).
"""
import os
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
# The name the automated tests' HTTP client uses. It is accepted only when the
# test suite asks for it: on an office network a machine really can be called
# "testserver", and a page served from it could otherwise rebind to this API.
_TEST_HOST = "testserver"

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # Everything the UI needs is bundled; nothing may load from, or send to,
    # another host. Inline styles are used by the React components.
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; worker-src 'self' blob:; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
}


async def local_guard(request, call_next):
    hostname = request.url.hostname
    if hostname not in _LOCAL_HOSTS and not (
        hostname == _TEST_HOST and os.environ.get("TARSIER_ALLOW_TEST_HOST") == "1"
    ):
        return JSONResponse({"detail": "Tarsier accepts local requests only."}, status_code=403)
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
            same = parsed.scheme == request.url.scheme and parsed.netloc == request.headers.get("host")
        except ValueError:
            same = False
        if not same:
            return JSONResponse({"detail": "Open Tarsier from its local app address."}, status_code=403)
    if request.url.path.startswith("/api/") and request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
        return JSONResponse({"detail": "Open Tarsier from its local app address."}, status_code=403)
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response
