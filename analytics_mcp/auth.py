"""Per-user Google credentials helper for the HTTP/OAuth server.

Bridges FastMCP's JWT session tokens with the Google OAuth tokens stored in
the TokenStore, producing google.oauth2.credentials.Credentials objects that
the GA4 API clients can use.
"""

import logging
import os

import google.auth.credentials
from google.oauth2.credentials import Credentials

from analytics_mcp.storage.base import TokenStore
from analytics_mcp.tools.utils import _READ_ONLY_ANALYTICS_SCOPE

logger = logging.getLogger(__name__)

# Module-level TokenStore instance, initialised by the HTTP server on startup.
_token_store: TokenStore | None = None


def init_token_store(store: TokenStore) -> None:
    """Set the module-level TokenStore used by get_user_credentials()."""
    global _token_store
    _token_store = store


async def get_user_credentials(user_id: str) -> Credentials | None:
    """Return Google OAuth credentials for a user, or None if unavailable.

    Args:
        user_id: The Google user ID (the ``sub`` claim from the FastMCP JWT).

    Returns:
        A ``google.oauth2.credentials.Credentials`` object ready for use with
        the GA4 API clients, or ``None`` if the user has no valid token.
    """
    if _token_store is None:
        logger.error("TokenStore not initialised. Call init_token_store() first.")
        return None

    token_data = await _token_store.get(user_id)
    if token_data is None:
        return None

    return Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        scopes=[_READ_ONLY_ANALYTICS_SCOPE],
    )
