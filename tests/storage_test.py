"""Unit tests for analytics_mcp/storage/gcs.py and analytics_mcp/auth.py.

GCS calls are mocked so these tests run without a real GCS bucket.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_KEY = Fernet.generate_key()
_TEST_BUCKET = "test-bucket"

_FUTURE = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
_PAST = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()

_SAMPLE_TOKEN = {
    "access_token": "ya29.test-access",
    "refresh_token": "1//test-refresh",
    "token_expiry": _FUTURE,
    "user_email": "test@example.com",
}


def _make_store():
    """Return a GCSTokenStore with mocked GCS client."""
    with (
        patch("analytics_mcp.storage.gcs.storage.Client"),
        patch.dict(
            "os.environ",
            {
                "GCS_BUCKET_NAME": _TEST_BUCKET,
                "TOKEN_ENCRYPTION_KEY": _TEST_KEY.decode(),
            },
        ),
    ):
        from analytics_mcp.storage.gcs import GCSTokenStore

        store = GCSTokenStore()
        mock_bucket = MagicMock()
        store._bucket = mock_bucket
        return store, mock_bucket


# ---------------------------------------------------------------------------
# GCSTokenStore tests
# ---------------------------------------------------------------------------


class TestGCSTokenStoreGet(unittest.IsolatedAsyncioTestCase):

    async def test_get_returns_none_when_blob_missing(self):
        store, mock_bucket = _make_store()
        mock_bucket.blob.return_value.download_as_bytes.side_effect = Exception("Not found")

        result = await store.get("user123")
        self.assertIsNone(result)

    async def test_get_returns_token_when_valid(self):
        store, mock_bucket = _make_store()
        encrypted = store._encrypt(_SAMPLE_TOKEN)
        mock_bucket.blob.return_value.download_as_bytes.return_value = encrypted

        result = await store.get("user123")
        self.assertEqual(result["access_token"], "ya29.test-access")
        self.assertEqual(result["user_email"], "test@example.com")

    async def test_get_refreshes_expired_token(self):
        store, mock_bucket = _make_store()
        expired_token = {**_SAMPLE_TOKEN, "token_expiry": _PAST}
        encrypted = store._encrypt(expired_token)
        mock_bucket.blob.return_value.download_as_bytes.return_value = encrypted

        refreshed_response = {
            "access_token": "ya29.new-access",
            "expires_in": 3600,
        }

        with patch(
            "analytics_mcp.storage.gcs.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.json.return_value = refreshed_response
            mock_resp.raise_for_status = MagicMock()
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await store.get("user123")

        self.assertIsNotNone(result)
        self.assertEqual(result["access_token"], "ya29.new-access")

    async def test_get_deletes_token_on_invalid_grant(self):
        store, mock_bucket = _make_store()
        expired_token = {**_SAMPLE_TOKEN, "token_expiry": _PAST}
        encrypted = store._encrypt(expired_token)
        mock_bucket.blob.return_value.download_as_bytes.return_value = encrypted

        import httpx

        with patch(
            "analytics_mcp.storage.gcs.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"error": "invalid_grant"}
            mock_resp.content = b'{"error": "invalid_grant"}'
            mock_http_error = httpx.HTTPStatusError(
                "invalid_grant", request=MagicMock(), response=mock_resp
            )
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=mock_http_error)
            mock_client_cls.return_value = mock_client

            result = await store.get("user123")

        self.assertIsNone(result)
        # delete() should have been called
        mock_bucket.blob.return_value.delete.assert_called()


class TestGCSTokenStoreSet(unittest.IsolatedAsyncioTestCase):

    async def test_set_encrypts_and_uploads(self):
        store, mock_bucket = _make_store()
        await store.set("user123", _SAMPLE_TOKEN)

        blob = mock_bucket.blob.return_value
        blob.upload_from_string.assert_called_once()
        # Verify the uploaded data is encrypted (not raw JSON)
        uploaded_bytes = blob.upload_from_string.call_args[0][0]
        self.assertNotIn(b"access_token", uploaded_bytes)
        # But can be decrypted back
        decrypted = store._decrypt(uploaded_bytes)
        self.assertEqual(decrypted["access_token"], "ya29.test-access")


class TestGCSTokenStoreDelete(unittest.IsolatedAsyncioTestCase):

    async def test_delete_calls_blob_delete(self):
        store, mock_bucket = _make_store()
        await store.delete("user123")
        mock_bucket.blob.return_value.delete.assert_called_once()

    async def test_delete_is_silent_on_error(self):
        store, mock_bucket = _make_store()
        mock_bucket.blob.return_value.delete.side_effect = Exception("Not found")
        # Should not raise
        await store.delete("user123")


# ---------------------------------------------------------------------------
# GCSTokenStore initialisation tests
# ---------------------------------------------------------------------------


class TestGCSTokenStoreInit(unittest.TestCase):

    def test_raises_without_bucket_name(self):
        with (
            patch("analytics_mcp.storage.gcs.storage.Client"),
            patch.dict("os.environ", {}, clear=True),
        ):
            # Need to reload to avoid cached env
            import importlib
            import analytics_mcp.storage.gcs as gcs_mod
            importlib.reload(gcs_mod)
            with self.assertRaises(ValueError, msg="Should raise without GCS_BUCKET_NAME"):
                gcs_mod.GCSTokenStore(encryption_key=_TEST_KEY)

    def test_raises_without_encryption_key(self):
        with (
            patch("analytics_mcp.storage.gcs.storage.Client"),
            patch.dict("os.environ", {"GCS_BUCKET_NAME": _TEST_BUCKET}, clear=False),
        ):
            import importlib
            import analytics_mcp.storage.gcs as gcs_mod
            importlib.reload(gcs_mod)
            with self.assertRaises(ValueError, msg="Should raise without TOKEN_ENCRYPTION_KEY"):
                gcs_mod.GCSTokenStore(bucket_name=_TEST_BUCKET)


# ---------------------------------------------------------------------------
# get_user_credentials tests
# ---------------------------------------------------------------------------


class TestGetUserCredentials(unittest.IsolatedAsyncioTestCase):

    async def test_returns_none_when_store_not_initialised(self):
        import analytics_mcp.auth as auth_mod
        auth_mod._token_store = None
        result = await auth_mod.get_user_credentials("user123")
        self.assertIsNone(result)

    async def test_returns_none_when_token_not_found(self):
        import analytics_mcp.auth as auth_mod
        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=None)
        auth_mod._token_store = mock_store

        result = await auth_mod.get_user_credentials("user123")
        self.assertIsNone(result)

    async def test_returns_credentials_when_token_found(self):
        import analytics_mcp.auth as auth_mod
        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=_SAMPLE_TOKEN)
        auth_mod._token_store = mock_store

        result = await auth_mod.get_user_credentials("user123")
        self.assertIsNotNone(result)
        self.assertEqual(result.token, "ya29.test-access")
        self.assertEqual(result.refresh_token, "1//test-refresh")


if __name__ == "__main__":
    unittest.main()
