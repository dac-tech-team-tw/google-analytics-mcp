# Cloud Run Deployment Quickstart

This guide deploys the GA4 MCP HTTP server to GCP Cloud Run.

Users connect with their Google account via OAuth — no local Python or gcloud installation required.

---

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Docker installed and authenticated to Artifact Registry

---

## Step 1: Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  analyticsdata.googleapis.com \
  analyticsadmin.googleapis.com \
  secretmanager.googleapis.com
```

---

## Step 2: Create Google OAuth Client

1. Go to [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials → OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Name: `GA4 MCP Server`
5. **Authorized redirect URIs**: add a placeholder for now (you will update this after deploy):
   ```
   http://localhost:8000/auth/callback
   ```
6. Click **Create** and note down the **Client ID** and **Client Secret**

---

## Step 3: Create Artifact Registry Repository

```bash
PROJECT_ID=$(gcloud config get-value project)
REGION="asia-east1"

gcloud artifacts repositories create analytics-mcp \
  --repository-format=docker \
  --location="${REGION}"
```

---

## Step 4: Build and Push Docker Image

```bash
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/analytics-mcp/analytics-mcp:latest"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"

docker build -t "${IMAGE}" .
docker push "${IMAGE}"
```

---

## Step 5: Generate JWT Signing Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Save the output — you will use it as `JWT_SIGNING_KEY`.

---

## Step 6: Deploy to Cloud Run

Replace the placeholder values before running:

```bash
PROJECT_ID=$(gcloud config get-value project)
REGION="asia-east1"
SERVICE_NAME="analytics-mcp"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/analytics-mcp/analytics-mcp:latest"

gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLIENT_ID=YOUR_CLIENT_ID" \
  --set-env-vars="GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET" \
  --set-env-vars="JWT_SIGNING_KEY=YOUR_JWT_SIGNING_KEY" \
  --set-env-vars="BASE_URL=https://placeholder.run.app" \
  --set-env-vars="ALLOW_DOMAINS=google.com|openai.com"
```

After deploy, get the actual service URL:

```bash
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --format="value(status.url)")
echo "${SERVICE_URL}"
```

Then update `BASE_URL` with the real URL:

```bash
gcloud run services update "${SERVICE_NAME}" \
  --region="${REGION}" \
  --set-env-vars="BASE_URL=${SERVICE_URL}"
```

---

## Step 7: Update OAuth Redirect URI

Go back to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials), edit your OAuth Client, and update **Authorized redirect URIs** to:

```
https://<your-service-url>/auth/callback
```

---

## Step 8: Connect Your MCP Client

### Claude Code

Run `/mcp` in Claude Code, add a new server with URL:
```
https://<your-service-url>/mcp
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "analytics-mcp": {
      "url": "https://<your-service-url>/mcp"
    }
  }
}
```

The first connection will open a browser window for Google login. After authorizing, all GA4 tools are available.

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Yes | OAuth 2.0 Client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth 2.0 Client Secret |
| `BASE_URL` | Yes | Public URL of the Cloud Run service (no trailing slash) |
| `JWT_SIGNING_KEY` | Yes | Secret for signing FastMCP session tokens (hex string) |
| `ALLOW_DOMAINS` | No | Pipe-delimited allowlist of exact email domains allowed to log in, e.g. `google.com|openai.com` |
| `PORT` | No | Port to listen on (Cloud Run sets this automatically, default 8000) |

### `ALLOW_DOMAINS` behavior

- `user@google.com` is allowed when `google.com` is listed
- `user@sub.google.com` is rejected unless `sub.google.com` is also listed
- If `ALLOW_DOMAINS` is unset or empty, any Google account may log in
- The allowlist is checked when the OAuth session is issued or refreshed, not on every MCP request

---

## One-Command Redeploy

After the initial setup, create a `deploy.sh` script (it is gitignored):

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="your-project-id"
REGION="asia-east1"
SERVICE_NAME="analytics-mcp"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/analytics-mcp/analytics-mcp:latest"

docker build -t "${IMAGE}" .
docker push "${IMAGE}"
gcloud run services update "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE}"

echo "Deployed:"
gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)"
```

Then deploy with:
```bash
bash deploy.sh
```

---

## Local Development

```bash
pip install -e ".[dev]"
cp .env.example .env
# Fill in .env with your values
analytics-mcp-http
```

The MCP endpoint will be available at `http://localhost:8000/mcp`.

Remember to add `http://localhost:8000/auth/callback` to your OAuth client's Authorized redirect URIs for local testing.

---

## Google OAuth Verification Warning

During login, users may see **"This app isn't verified"**. This is expected while the OAuth app is in Testing mode.

**For internal teams**: Add team members' Google accounts to the [Test users](https://console.cloud.google.com/apis/credentials/consent) list. They can proceed by clicking **Advanced → Go to (unsafe)**.

**For public deployment**: Submit your app for [Google OAuth verification](https://support.google.com/cloud/answer/9110914). You will need a Privacy Policy URL and the `analytics.readonly` scope justification.

---

## Rollback

```bash
# List revisions
gcloud run revisions list --service "${SERVICE_NAME}" --region "${REGION}"

# Roll back to a specific revision
gcloud run services update-traffic "${SERVICE_NAME}" \
  --region "${REGION}" \
  --to-revisions REVISION_NAME=100
```
