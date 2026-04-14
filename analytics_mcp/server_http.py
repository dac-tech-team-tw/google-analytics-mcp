"""HTTP Streamable MCP server with Google OAuth.

Starts a FastMCP server over HTTP (streamable transport), protected by Google
OAuth 2.0.  Users authenticate with their Google account; the server uses
their OAuth credentials to call the GA4 API on their behalf.

Entry point: ``analytics-mcp-http`` (see pyproject.toml).

Environment variables: see .env.example.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from analytics_mcp.auth_provider import create_google_provider
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

    FastMCP's GoogleProvider acts as an OAuth proxy: it holds the Google
    refresh token internally and always passes a valid Google access token
    as the Bearer token on each request.  We extract that access token via
    ``get_access_token().token`` and build a ``google.oauth2.credentials.Credentials``
    object directly — no secondary token store required.
    """
    import functools

    import google.oauth2.credentials

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            from fastmcp.server.dependencies import get_access_token
            token = get_access_token()
            google_access_token = token.token
        except Exception:
            return _AUTH_REQUIRED_ERROR

        if not google_access_token:
            return _AUTH_REQUIRED_ERROR

        credentials = google.oauth2.credentials.Credentials(
            token=google_access_token
        )

        # Set the contextvar for this async task so all nested calls to
        # create_*_api_client() use this user's credentials.
        ctx_token = _current_credentials.set(credentials)
        try:
            return await func(*args, **kwargs)
        finally:
            _current_credentials.reset(ctx_token)

    return wrapper


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialise shared resources at startup."""
    logger.info("GA4 MCP HTTP server starting up.")
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
