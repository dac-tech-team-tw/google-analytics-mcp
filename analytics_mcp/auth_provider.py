"""Google OAuth provider configuration for the FastMCP HTTP server.

Reads credentials from environment variables.  On Cloud Run, inject these
via Secret Manager references or the service's environment variable settings.

Required environment variables:
    GOOGLE_CLIENT_ID      - Google OAuth 2.0 client ID
    GOOGLE_CLIENT_SECRET  - Google OAuth 2.0 client secret
    BASE_URL              - Public base URL of this server (no trailing slash)
    JWT_SIGNING_KEY       - Hex string used to sign FastMCP session JWTs
"""

import os

from fastmcp.server.auth.providers.google import GoogleProvider

# Scopes requested during the OAuth flow.
# analytics.readonly gives access to all GA4 API calls in this server.
_REQUIRED_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/analytics.readonly",
]


def create_google_provider() -> GoogleProvider:
    """Build and return a configured GoogleProvider.

    Raises:
        ValueError: If any required environment variable is missing.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    base_url = os.environ.get("BASE_URL")
    jwt_signing_key = os.environ.get("JWT_SIGNING_KEY")

    missing = [
        name
        for name, val in [
            ("GOOGLE_CLIENT_ID", client_id),
            ("GOOGLE_CLIENT_SECRET", client_secret),
            ("BASE_URL", base_url),
            ("JWT_SIGNING_KEY", jwt_signing_key),
        ]
        if not val
    ]
    if missing:
        raise ValueError(
            f"Missing required environment variables for OAuth: {', '.join(missing)}. "
            "See .env.example for setup instructions."
        )

    return GoogleProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        required_scopes=_REQUIRED_SCOPES,
        jwt_signing_key=jwt_signing_key,
    )
