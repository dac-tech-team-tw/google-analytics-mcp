"""GCS-backed token storage with Fernet encryption and automatic token refresh.

Required environment variables:
    GCS_BUCKET_NAME       - Name of the GCS bucket (must be private).
    TOKEN_ENCRYPTION_KEY  - Fernet key for encrypting token data at rest.
                            Generate: python -c "from cryptography.fernet import
                            Fernet; print(Fernet.generate_key().decode())"

The Cloud Run service account needs ``roles/storage.objectAdmin`` on the bucket.
"""

import json
import logging
import os
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken
from google.cloud import storage

from analytics_mcp.storage.base import TokenStore

logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_TOKEN_PATH_PREFIX = "tokens/"


class GCSTokenStore(TokenStore):
    """Stores per-user Google OAuth tokens in a GCS bucket.

    Tokens are encrypted with Fernet before upload. GCS provides an additional
    layer of encryption at rest.

    Each user's token is stored at:
        gs://{bucket_name}/tokens/{google_user_id}.enc
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        encryption_key: bytes | str | None = None,
    ) -> None:
        """Initialise the store.

        Args:
            bucket_name: GCS bucket name. Defaults to the ``GCS_BUCKET_NAME``
                environment variable.
            encryption_key: Fernet key (bytes or base64 string). Defaults to
                the ``TOKEN_ENCRYPTION_KEY`` environment variable.

        Raises:
            ValueError: If bucket_name or encryption_key cannot be resolved.
        """
        bucket_name = bucket_name or os.environ.get("GCS_BUCKET_NAME")
        if not bucket_name:
            raise ValueError(
                "GCS_BUCKET_NAME environment variable is not set. "
                "Set it to the name of your GCS bucket for token storage."
            )

        raw_key = encryption_key or os.environ.get("TOKEN_ENCRYPTION_KEY")
        if not raw_key:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY environment variable is not set. "
                "Generate one with: python -c \"from cryptography.fernet "
                "import Fernet; print(Fernet.generate_key().decode())\""
            )

        if isinstance(raw_key, str):
            raw_key = raw_key.encode()

        self._bucket = storage.Client().bucket(bucket_name)
        self._fernet = Fernet(raw_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _blob(self, user_id: str):
        return self._bucket.blob(f"{_TOKEN_PATH_PREFIX}{user_id}.enc")

    def _encrypt(self, data: dict) -> bytes:
        return self._fernet.encrypt(json.dumps(data).encode())

    def _decrypt(self, data: bytes) -> dict:
        return json.loads(self._fernet.decrypt(data))

    def _is_expired(self, token_data: dict) -> bool:
        expiry_str = token_data.get("token_expiry")
        if not expiry_str:
            return True
        try:
            expiry = datetime.fromisoformat(expiry_str)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= expiry
        except ValueError:
            return True

    async def _refresh_access_token(
        self, user_id: str, token_data: dict
    ) -> dict | None:
        """Use the refresh token to obtain a new access token from Google.

        Writes the updated token back to GCS on success.
        Deletes the stored token and returns None on ``invalid_grant``.
        """
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            logger.warning("No refresh_token for user %s; deleting token.", user_id)
            await self.delete(user_id)
            return None

        google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _GOOGLE_TOKEN_ENDPOINT,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": google_client_id,
                        "client_secret": google_client_secret,
                    },
                )
                resp.raise_for_status()
                refreshed = resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.json() if exc.response.content else {}
            if body.get("error") == "invalid_grant":
                logger.warning(
                    "Refresh token invalid for user %s; deleting token.", user_id
                )
                await self.delete(user_id)
                return None
            logger.error(
                "Token refresh failed for user %s: %s", user_id, exc
            )
            return None
        except Exception as exc:
            logger.error("Token refresh error for user %s: %s", user_id, exc)
            return None

        from datetime import timedelta

        expires_in = refreshed.get("expires_in", 3600)
        new_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        updated = {
            **token_data,
            "access_token": refreshed["access_token"],
            "token_expiry": new_expiry.isoformat(),
        }
        # Google only returns a new refresh_token if it has rotated.
        if "refresh_token" in refreshed:
            updated["refresh_token"] = refreshed["refresh_token"]

        await self.set(user_id, updated)
        return updated

    # ------------------------------------------------------------------
    # TokenStore interface
    # ------------------------------------------------------------------

    async def get(self, user_id: str) -> dict | None:
        """Retrieve and, if necessary, refresh the token for a user."""
        blob = self._blob(user_id)
        try:
            encrypted = blob.download_as_bytes()
        except Exception:
            return None

        try:
            token_data = self._decrypt(encrypted)
        except InvalidToken:
            logger.error("Decryption failed for user %s; deleting token.", user_id)
            await self.delete(user_id)
            return None

        if self._is_expired(token_data):
            return await self._refresh_access_token(user_id, token_data)

        return token_data

    async def set(self, user_id: str, token_data: dict) -> None:
        """Encrypt and upload token data to GCS."""
        blob = self._blob(user_id)
        blob.upload_from_string(
            self._encrypt(token_data),
            content_type="application/octet-stream",
        )

    async def delete(self, user_id: str) -> None:
        """Delete a user's token from GCS (silent if not found)."""
        try:
            self._blob(user_id).delete()
        except Exception:
            pass
