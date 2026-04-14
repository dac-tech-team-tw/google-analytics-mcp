"""HTTP Streamable MCP server with Google OAuth.

Starts a FastMCP server over HTTP (streamable transport), protected by Google
OAuth 2.0.  Users authenticate with their Google account; the server uses
their OAuth credentials to call the GA4 API on their behalf.

Entry point: ``analytics-mcp-http`` (see pyproject.toml).

Environment variables: see .env.example.
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from contextvars import copy_context
from typing import Any, Dict, List

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from analytics_mcp.auth import get_user_credentials, init_token_store
from analytics_mcp.auth_provider import create_google_provider
from analytics_mcp.storage.gcs import GCSTokenStore
from analytics_mcp.tools.utils import _current_credentials

# GA4 tool implementations (unchanged from stdio version)
from analytics_mcp.tools.admin.info import (
    get_account_summaries,
    get_property_details,
    list_google_ads_links,
    list_property_annotations,
)
from analytics_mcp.tools.reporting.core import run_report, _run_report_description
from analytics_mcp.tools.reporting.metadata import get_custom_dimensions_and_metrics
from analytics_mcp.tools.reporting.realtime import (
    run_realtime_report,
    _run_realtime_report_description,
)

logger = logging.getLogger(__name__)

_AUTH_REQUIRED_ERROR = (
    "Error: Authentication required. "
    "Please reconnect to re-authorize with Google."
)

# ---------------------------------------------------------------------------
# Credential injection wrapper
# ---------------------------------------------------------------------------

def _with_user_credentials(func):
    """Wrap a GA4 tool to inject per-user Google credentials via contextvar.

    Before calling the underlying function, resolves the authenticated user's
    Google credentials from the TokenStore and sets the ``_current_credentials``
    contextvar so that ``create_*_api_client()`` picks them up automatically.

    Returns the _AUTH_REQUIRED_ERROR string when credentials are unavailable.
    """
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            from fastmcp.server.dependencies import get_access_token
            token = get_access_token()
            user_id = token.claims.get("sub")
        except Exception:
            return _AUTH_REQUIRED_ERROR

        if not user_id:
            return _AUTH_REQUIRED_ERROR

        credentials = await get_user_credentials(user_id)
        if credentials is None:
            return _AUTH_REQUIRED_ERROR

        # Set the contextvar for this async task so all nested calls to
        # create_*_api_client() use this user's credentials.
        ctx_token = _current_credentials.set(credentials)
        try:
            return await func(*args, **kwargs)
        finally:
            _current_credentials.reset(ctx_token)

    return wrapper


# ---------------------------------------------------------------------------
# OAuth callback interceptor
# ---------------------------------------------------------------------------
# FastMCP's GoogleProvider handles /auth/callback internally.
# We add an additional route /auth/store-token that is called BEFORE the
# standard callback via a redirect chain, so we can capture and persist the
# Google access token for use in GA4 API calls.
#
# Flow:
#   Google → /auth/callback (GoogleProvider) → issues FastMCP JWT
#
# GoogleProvider stores the OAuth tokens internally.  We intercept the
# callback by patching the provider's _handle_callback method after the
# server is initialised so we can persist tokens to GCSTokenStore.

def _patch_provider_callback(provider, token_store):
    """Monkey-patch GoogleProvider to persist GA4 tokens to our TokenStore.

    Called once during lifespan startup after the provider is created.
    """
    original_handle = getattr(provider, "_handle_callback", None)
    if original_handle is None:
        logger.warning(
            "GoogleProvider._handle_callback not found; "
            "GA4 token persistence will not work."
        )
        return

    import functools

    @functools.wraps(original_handle)
    async def patched_handle_callback(request: Request):
        # Run the original handler first so GoogleProvider validates the flow
        response = await original_handle(request)

        # Try to extract and store the Google tokens from GoogleProvider's
        # internal state.  GoogleProvider stores token info as attributes set
        # during the callback; we access them via the request's app state.
        try:
            state = getattr(request.state, "_ga4_token_data", None)
            if state:
                await token_store.set(state["user_id"], state)
        except Exception as exc:
            logger.warning("Could not persist GA4 token: %s", exc)

        return response

    provider._handle_callback = patched_handle_callback


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialise shared resources at startup."""
    token_store = GCSTokenStore()
    init_token_store(token_store)
    logger.info("GCSTokenStore initialised.")
    yield
    logger.info("GA4 MCP HTTP server shutting down.")


# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------

def create_app() -> FastMCP:
    """Build and return the configured FastMCP application."""
    auth_provider = create_google_provider()

    mcp = FastMCP(
        name="Google Analytics MCP Server",
        auth=auth_provider,
        lifespan=lifespan,
    )

    # Register all GA4 tools, wrapped for per-user credential injection.
    mcp.tool()(_with_user_credentials(get_account_summaries))
    mcp.tool()(_with_user_credentials(list_google_ads_links))
    mcp.tool()(_with_user_credentials(get_property_details))
    mcp.tool()(_with_user_credentials(list_property_annotations))
    mcp.tool()(_with_user_credentials(get_custom_dimensions_and_metrics))

    # run_report and run_realtime_report get richer descriptions.
    run_report_tool = _with_user_credentials(run_report)
    run_report_tool.__doc__ = _run_report_description()
    mcp.tool()(run_report_tool)

    run_realtime_tool = _with_user_credentials(run_realtime_report)
    run_realtime_tool.__doc__ = _run_realtime_report_description()
    mcp.tool()(run_realtime_tool)

    return mcp


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_server() -> None:
    """Start the FastMCP HTTP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    port = int(os.environ.get("PORT", 8000))
    app = create_app()

    logger.info("Starting GA4 MCP HTTP server on 0.0.0.0:%d", port)
    app.run(transport="http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run_server()
