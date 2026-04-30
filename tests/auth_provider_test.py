# Copyright 2025 Google LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test cases for OAuth provider domain allowlist behavior."""

from types import SimpleNamespace
import unittest

from analytics_mcp import auth_provider


class TestAllowDomainsHelpers(unittest.TestCase):
    """Test cases for allowlist parsing and matching helpers."""

    def test_parse_allowed_domains(self):
        """Parses pipe-delimited domains into a normalized allowlist."""
        self.assertEqual(auth_provider.parse_allowed_domains(None), set())
        self.assertEqual(auth_provider.parse_allowed_domains(""), set())
        self.assertEqual(
            auth_provider.parse_allowed_domains(" OpenAI.com | google.com|| "),
            {"openai.com", "google.com"},
        )

    def test_extract_email_domain(self):
        """Extracts a normalized domain from a valid email address."""
        self.assertEqual(
            auth_provider.extract_email_domain("User@OpenAI.com"),
            "openai.com",
        )
        self.assertIsNone(auth_provider.extract_email_domain(None))
        self.assertIsNone(auth_provider.extract_email_domain(""))
        self.assertIsNone(auth_provider.extract_email_domain("not-an-email"))

    def test_is_email_allowed(self):
        """Matches exact email domains against the allowlist."""
        self.assertTrue(auth_provider.is_email_allowed("user@gmail.com", set()))
        self.assertTrue(
            auth_provider.is_email_allowed(
                "user@openai.com", {"openai.com", "google.com"}
            )
        )
        self.assertFalse(
            auth_provider.is_email_allowed(
                "user@sub.openai.com", {"openai.com", "google.com"}
            )
        )
        self.assertFalse(
            auth_provider.is_email_allowed(
                "user@gmail.com", {"openai.com", "google.com"}
            )
        )


class _FakeTokenVerifier:
    """Minimal async token verifier stub for provider tests."""

    def __init__(self, result):
        self.result = result

    async def verify_token(self, token):
        return self.result


class TestAllowedDomainsGoogleProvider(unittest.IsolatedAsyncioTestCase):
    """Test cases for provider-side domain enforcement."""

    async def test_extract_upstream_claims_allows_matching_domain(self):
        """Allows token issuance when the user email matches allowlist."""
        provider = auth_provider.AllowedDomainsGoogleProvider.__new__(
            auth_provider.AllowedDomainsGoogleProvider
        )
        provider._allowed_domains = {"openai.com"}
        provider._token_validator = _FakeTokenVerifier(
            SimpleNamespace(
                claims={
                    "sub": "user-123",
                    "aud": "client-123",
                    "email": "user@openai.com",
                }
            )
        )

        claims = await provider._extract_upstream_claims(
            {"access_token": "google-access-token"}
        )

        self.assertEqual(claims["email"], "user@openai.com")

    async def test_extract_upstream_claims_rejects_disallowed_domain(self):
        """Rejects token issuance when the user email is outside allowlist."""
        provider = auth_provider.AllowedDomainsGoogleProvider.__new__(
            auth_provider.AllowedDomainsGoogleProvider
        )
        provider._allowed_domains = {"openai.com"}
        provider._token_validator = _FakeTokenVerifier(
            SimpleNamespace(
                claims={
                    "sub": "user-123",
                    "aud": "client-123",
                    "email": "user@gmail.com",
                }
            )
        )

        with self.assertRaisesRegex(Exception, "not allowed"):
            await provider._extract_upstream_claims(
                {"access_token": "google-access-token"}
            )
