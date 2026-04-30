"""Google OAuth provider configuration for the FastMCP HTTP server.

Reads credentials from environment variables.  On Cloud Run, inject these
via Secret Manager references or the service's environment variable settings.

Required environment variables:
    GOOGLE_CLIENT_ID      - Google OAuth 2.0 client ID
    GOOGLE_CLIENT_SECRET  - Google OAuth 2.0 client secret
    BASE_URL              - Public base URL of this server (no trailing slash)
    JWT_SIGNING_KEY       - Hex string used to sign FastMCP session JWTs

Optional environment variables:
    ALLOW_DOMAINS         - Pipe-delimited email domain allowlist
"""

import os

from mcp.server.auth.provider import TokenError
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

# Scopes requested during the OAuth flow.
# analytics.readonly gives access to all GA4 API calls in this server.
_REQUIRED_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/analytics.readonly",
]


def parse_allowed_domains(raw_value: str | None) -> set[str]:
    """Parse a pipe-delimited domain allowlist from environment config."""
    if not raw_value:
        return set()

    return {domain.strip().lower() for domain in raw_value.split("|") if domain.strip()}


def extract_email_domain(email: str | None) -> str | None:
    """Return the normalized domain for an email address."""
    if not email or "@" not in email:
        return None

    local_part, _, domain = email.strip().rpartition("@")
    if not local_part or not domain:
        return None

    return domain.lower()


def is_email_allowed(email: str | None, allowed_domains: set[str]) -> bool:
    """Return True when the email matches the configured allowlist."""
    if not allowed_domains:
        return True

    domain = extract_email_domain(email)
    if domain is None:
        return False

    return domain in allowed_domains


class AllowedDomainsGoogleProvider(GoogleProvider):
    """GoogleProvider variant that restricts logins by email domain."""

    def __init__(self, *, allowed_domains: set[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._allowed_domains = set(allowed_domains or set())

    async def _extract_upstream_claims(self, idp_tokens: dict) -> dict | None:
        """Verify Google claims and reject disallowed email domains."""
        access_token = idp_tokens.get("access_token")
        if not access_token:
            raise TokenError(
                "invalid_grant",
                "Google access token missing from OAuth response.",
            )

        validated = await self._token_validator.verify_token(access_token)
        if validated is None:
            raise TokenError(
                "invalid_grant",
                "Failed to verify the Google account after login.",
            )

        claims = dict(validated.claims or {})
        email = claims.get("email")
        if not is_email_allowed(email, self._allowed_domains):
            logger.warning(
                "Rejected Google login for disallowed domain: %s",
                extract_email_domain(email) or "unknown",
            )
            raise TokenError(
                "invalid_grant",
                "This Google account is not allowed to use this server.",
            )

        return claims


def create_google_provider() -> GoogleProvider:
    """Build and return a configured GoogleProvider.

    Raises:
        ValueError: If any required environment variable is missing.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    base_url = os.environ.get("BASE_URL")
    jwt_signing_key = os.environ.get("JWT_SIGNING_KEY")
    allowed_domains = parse_allowed_domains(os.environ.get("ALLOW_DOMAINS"))

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

    if allowed_domains:
        logger.info(
            "ALLOW_DOMAINS enabled for %d domain(s).",
            len(allowed_domains),
        )
    else:
        logger.info("ALLOW_DOMAINS not set; allowing all Google accounts.")

    return AllowedDomainsGoogleProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        required_scopes=_REQUIRED_SCOPES,
        jwt_signing_key=jwt_signing_key,
        allowed_domains=allowed_domains,
    )
