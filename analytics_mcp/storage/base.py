"""Abstract token storage interface.

Implement this class to use a custom storage backend (Redis, Firestore, etc.).
The default implementation is GCSTokenStore (see gcs.py).

Token data schema stored per user:
{
    "access_token":  str,   # Google OAuth access token
    "refresh_token": str,   # Google OAuth refresh token (long-lived)
    "token_expiry":  str,   # ISO 8601 UTC expiry of access_token
    "user_email":    str,   # Google account email
}
"""

from abc import ABC, abstractmethod


class TokenStore(ABC):
    """Abstract base class for per-user OAuth token storage."""

    @abstractmethod
    async def get(self, user_id: str) -> dict | None:
        """Retrieve token data for a user.

        Implementations SHOULD refresh the access token automatically if it
        has expired, using the stored refresh_token.

        Args:
            user_id: The Google user ID (the ``sub`` claim from the ID token).

        Returns:
            A dict with keys ``access_token``, ``refresh_token``,
            ``token_expiry``, and ``user_email``, or ``None`` if the user has
            no stored token or the refresh token is no longer valid.
        """

    @abstractmethod
    async def set(self, user_id: str, token_data: dict) -> None:
        """Persist token data for a user.

        Args:
            user_id: The Google user ID.
            token_data: Dict with keys as described in the module docstring.
        """

    @abstractmethod
    async def delete(self, user_id: str) -> None:
        """Delete token data for a user.

        Silently succeeds if the user has no stored token.

        Args:
            user_id: The Google user ID.
        """
