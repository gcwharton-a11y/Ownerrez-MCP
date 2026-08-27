"""Remote (HTTP) entrypoint for the OwnerRez MCP server.

This wraps the same tools defined in ``ownerrez_mcp/server.py`` (bookings,
properties, guests, financials, guest messaging, webhooks) with Streamable
HTTP transport so it can be deployed as a standalone web service and added
to Claude as a **custom connector**.

Because this exposes real access to an OwnerRez account over the public
internet, every request must present a static bearer token that matches the
``MCP_ACCESS_TOKEN`` environment variable. This matches Claude's
"static_headers" custom-connector auth type: an org admin enters the token
once when adding the connector, and Claude sends it as an ``Authorization``
header on every request. See README.md for setup.

Run locally:
    MCP_ACCESS_TOKEN=devtoken OWNERREZ_USERNAME=... OWNERREZ_TOKEN=... \
        uvicorn http_app:app --host 0.0.0.0 --port 8080

In production, PORT and all OWNERREZ_*/MCP_ACCESS_TOKEN vars come from the
hosting platform's environment (see render.yaml / Dockerfile).
"""

from __future__ import annotations

import hmac
import os

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from ownerrez_mcp.server import mcp

# Paths that must stay reachable without a token (platform health checks).
_PUBLIC_PATHS = {"/health", "/healthz"}


def _expected_token() -> str | None:
    return os.getenv("MCP_ACCESS_TOKEN") or None


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Rejects any request that doesn't carry the shared MCP access token.

    Accepts ``Authorization: Bearer <token>`` (what Claude's static_headers
    auth sends) or a raw ``X-MCP-Access-Token: <token>`` header, for
    flexibility when testing with curl or other MCP clients.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        expected = _expected_token()
        if not expected:
            # Fail closed: never serve OwnerRez data with no token configured.
            return JSONResponse(
                {"error": "server misconfigured: MCP_ACCESS_TOKEN is not set"},
                status_code=500,
            )

        supplied = request.headers.get("x-mcp-access-token")
        if not supplied:
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                supplied = auth_header[7:].strip()

        if not supplied or not hmac.compare_digest(supplied, expected):
            return JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="ownerrez-mcp"'},
            )

        return await call_next(request)


async def health(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


# Build the MCP Streamable HTTP app. It's mounted at /mcp below, so the
# sub-app's own path is left at "/" (avoids a doubled "/mcp/mcp").
mcp_app = mcp.http_app(
    path="/",
    transport="streamable-http",
    middleware=[Middleware(BearerAuthMiddleware)],
)

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/healthz", health),
        Mount("/mcp", app=mcp_app),
    ],
    # The MCP sub-app manages the streamable-http session machinery in its
    # own lifespan; it must run for the mount to work.
    lifespan=mcp_app.lifespan,
)
