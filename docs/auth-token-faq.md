# OAuth Token Lifecycle — FAQ

This document explains how Google OAuth tokens work in this server, what happens when they expire, and answers common questions.

---

## How tokens flow through the system

```
User browser
    │
    │  1. Google login (OAuth consent screen)
    ▼
Google OAuth
    │
    │  2. Returns access_token (60 min) + refresh_token (long-lived)
    ▼
FastMCP GoogleProvider  ← holds refresh_token internally
    │
    │  3. On each MCP request, passes access_token as Bearer token
    ▼
_with_user_credentials wrapper
    │
    │  4. Wraps token in google.oauth2.credentials.Credentials
    ▼
GA4 API client
```

There are **two types of tokens** in play:

| Token | Lifespan | Held by | Purpose |
|---|---|---|---|
| **Access token** | ~60 minutes | MCP client session | Authorizes GA4 API calls |
| **Refresh token** | Until revoked | FastMCP GoogleProvider | Obtains new access tokens silently |

---

## Q&A

### Q: Do users need to re-login every 60 minutes?

**No.** FastMCP's `GoogleProvider` holds the refresh token and automatically obtains a new access token before the old one expires. From the user's perspective, the session stays alive indefinitely without any action required.

---

### Q: What triggers a re-login?

Users need to re-authenticate only when:

- **The refresh token is revoked** — the user manually revokes access in their [Google Account settings](https://myaccount.google.com/permissions), or an admin revokes it via Google Workspace.
- **The OAuth consent screen changes** — if you add new scopes to the app, existing sessions become invalid.
- **The MCP client disconnects and reconnects** — depending on the client, it may restart the OAuth flow on reconnect. Claude Code, for example, stores the session token locally and reuses it across restarts.
- **Cloud Run restarts and loses session state** — see below.

---

### Q: What does `ALLOW_DOMAINS` do?

`ALLOW_DOMAINS` is an optional environment variable that restricts which Google
accounts may complete OAuth login for this server.

Example:

```bash
ALLOW_DOMAINS=google.com|openai.com
```

Behavior:

- `user@google.com` is allowed
- `user@openai.com` is allowed
- `user@sub.openai.com` is rejected unless `sub.openai.com` is explicitly listed
- if `ALLOW_DOMAINS` is unset or empty, any Google account may log in

The match is based on the exact email domain and is case-insensitive.

---

### Q: Why do I see `invalid_grant: This Google account is not allowed to use this server.`?

This is the expected error when the OAuth flow succeeds, but the Google
account's email domain is not included in `ALLOW_DOMAINS`.

The rejection happens during OAuth session issuance or refresh, before the user
receives a usable MCP session token.

Common causes:

- the email domain is not listed in `ALLOW_DOMAINS`
- a parent domain is listed but the actual account uses a subdomain
- the Cloud Run service is still serving an older revision without the latest environment variable change

---

### Q: What happens when Cloud Run restarts?

FastMCP's `GoogleProvider` stores OAuth session state (including the refresh token) using `client_storage`, which defaults to the **local file system** via `platformdirs`.

Cloud Run containers are ephemeral — a restart or a new instance starts with an empty file system. This means **FastMCP loses its session state**, and users will need to re-authenticate.

This affects availability, not security. The next login re-grants the refresh token and restores the session.

**Mitigation options** (not implemented in this repo):

- Pass a custom `client_storage` backed by Cloud Firestore or Cloud Memorystore (Redis) to `GoogleProvider`, so session state survives restarts and is shared across instances.
- Set `--min-instances=1` on Cloud Run to reduce cold starts (does not prevent all restarts).

---

### Q: What is `expiry=now+55min` in the code?

In `server_http.py`, each tool call builds a temporary credentials object:

```python
credentials = google.oauth2.credentials.Credentials(
    token=google_access_token,
    expiry=datetime.datetime.utcnow() + datetime.timedelta(minutes=55),
)
```

This object is **created fresh on every tool call** from the access token that FastMCP just provided. The `expiry` field is metadata that tells the `google-auth` library "this token is fresh, do not attempt to refresh it."

Without `expiry`, some code paths in `google-auth` see `expiry=None` and may try to call `credentials.refresh()` as a precaution. Our credentials object has no `refresh_token` or `token_uri`, so that would raise a `RefreshError`.

**55 minutes** is a conservative value slightly below Google's actual 60-minute access token lifetime. It could equally be `timedelta(hours=1)`. The exact value does not matter — by the time the next tool call arrives, a new credentials object is built from a fresh token.

---

### Q: What if a GA4 report query takes longer than 55 minutes?

Not a concern in practice. The `expiry` only prevents `google-auth` from trying to refresh the credentials object — it does not interrupt an in-flight API call. GA4 report queries typically complete in under 30 seconds. The 55-minute window is there purely to prevent a spurious refresh attempt at the start of the call.

---

### Q: What happens if the GA4 API call fails because the token expired mid-flight?

Google's API returns HTTP 401. The `google-analytics-data` gRPC client will surface this as a `google.api_core.exceptions.Unauthenticated` exception, which propagates back to the MCP tool as an error response. The user sees an error message from the tool; they do not need to re-authenticate — the next tool call will receive a fresh token from FastMCP automatically.

---

### Q: Is the access token logged anywhere?

The access token appears in Cloud Run logs when FastMCP logs outbound HTTP requests at DEBUG level (e.g., calls to `tokeninfo` and `userinfo`). The default log level in this server is INFO, so tokens are not logged in normal operation.

If you enable DEBUG logging for troubleshooting, be aware that tokens may appear in log output and ensure your Cloud Logging access controls are restricted appropriately.

---

### Q: What scopes does the token include?

The OAuth consent screen requests these scopes (configured in `auth_provider.py`):

| Scope | Purpose |
|---|---|
| `openid` | OpenID Connect identity |
| `email` | User's email address |
| `profile` | User's name and picture |
| `https://www.googleapis.com/auth/analytics.readonly` | Read-only access to all GA4 properties the user has access to |

The server only reads GA4 data. No write operations are performed.

---

### Q: Can a user access GA4 properties they don't own?

No. The access token belongs to the authenticated user. GA4 API calls made with their token can only access properties that user's Google account has been granted access to in GA4. There is no privilege escalation — each user sees exactly what they would see in the GA4 web interface.

---

### Q: Is `ALLOW_DOMAINS` checked on every MCP request?

No. In this server, `ALLOW_DOMAINS` is checked when FastMCP issues or refreshes
the OAuth session. It is not re-checked on every MCP request.

This keeps request handling simple and avoids adding per-request authorization
overhead. If you change `ALLOW_DOMAINS`, validate the new behavior with a fresh
login.
