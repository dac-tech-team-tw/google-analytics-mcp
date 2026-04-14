# Deploying GA4 MCP HTTP Server to Cloud Run

This guide deploys the HTTP/OAuth version of the GA4 MCP server to GCP Cloud Run.

---

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth login`)
- Docker installed (for local testing only)

---

## Step 1: Create GCS Bucket for Token Storage

```bash
PROJECT_ID=$(gcloud config get-value project)
BUCKET_NAME="${PROJECT_ID}-ga4-mcp-tokens"

# Create a private bucket (no public access)
gcloud storage buckets create "gs://${BUCKET_NAME}" \
  --location=asia-east1 \
  --uniform-bucket-level-access

# Verify public access is blocked
gcloud storage buckets describe "gs://${BUCKET_NAME}" \
  --format="value(iamConfiguration.publicAccessPrevention)"
# Expected: enforced
```

---

## Step 2: Create a Service Account for Cloud Run

```bash
SA_NAME="ga4-mcp-server"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="GA4 MCP HTTP Server"

# Grant Storage access (for token storage)
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

# Grant Secret Manager access
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
```

---

## Step 3: Configure Google OAuth Client

1. Go to [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name: `GA4 MCP Server`
5. **Authorized redirect URIs**: add your Cloud Run URL + `/auth/callback`
   - Example: `https://ga4-mcp-server-xxxx-uc.a.run.app/auth/callback`
   - For local dev: `http://localhost:8000/auth/callback`
6. Download the client credentials (you'll need `client_id` and `client_secret`)

Also enable the required APIs:
```bash
gcloud services enable \
  analyticsdata.googleapis.com \
  analyticsadmin.googleapis.com \
  secretmanager.googleapis.com
```

---

## Step 4: Store Secrets in Secret Manager

```bash
# Generate keys
FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
JWT_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# Store in Secret Manager
echo -n "${FERNET_KEY}" | gcloud secrets create ga4-mcp-token-encryption-key \
  --data-file=- --replication-policy=automatic

echo -n "${JWT_KEY}" | gcloud secrets create ga4-mcp-jwt-signing-key \
  --data-file=- --replication-policy=automatic

# Store OAuth credentials (replace with your actual values)
echo -n "YOUR_GOOGLE_CLIENT_SECRET" | gcloud secrets create ga4-mcp-google-client-secret \
  --data-file=- --replication-policy=automatic
```

---

## Step 5: Deploy to Cloud Run

```bash
SERVICE_NAME="ga4-mcp-server"
REGION="asia-east1"
CLOUD_RUN_URL="https://${SERVICE_NAME}-xxxx-uc.a.run.app"  # update after first deploy

# Build and push image
gcloud builds submit --tag "gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Deploy
gcloud run deploy "${SERVICE_NAME}" \
  --image "gcr.io/${PROJECT_ID}/${SERVICE_NAME}" \
  --platform managed \
  --region "${REGION}" \
  --service-account "${SA_EMAIL}" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLIENT_ID=YOUR_CLIENT_ID" \
  --set-env-vars "BASE_URL=${CLOUD_RUN_URL}" \
  --set-env-vars "GCS_BUCKET_NAME=${BUCKET_NAME}" \
  --set-secrets "GOOGLE_CLIENT_SECRET=ga4-mcp-google-client-secret:latest" \
  --set-secrets "TOKEN_ENCRYPTION_KEY=ga4-mcp-token-encryption-key:latest" \
  --set-secrets "JWT_SIGNING_KEY=ga4-mcp-jwt-signing-key:latest"
```

After the first deploy, update `BASE_URL` with the actual Cloud Run URL and redeploy:
```bash
CLOUD_RUN_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --format="value(status.url)")

gcloud run services update "${SERVICE_NAME}" \
  --region "${REGION}" \
  --set-env-vars "BASE_URL=${CLOUD_RUN_URL}"
```

Also add the Cloud Run URL to your Google OAuth client's **Authorized redirect URIs**.

---

## Step 6: Connect from Claude Desktop / MCP Client

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "ga4": {
      "url": "https://ga4-mcp-server-xxxx-uc.a.run.app/mcp",
      "auth": "oauth"
    }
  }
}
```

The first connection will open a browser window for Google login.

---

## Local Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your values

# Run the HTTP server
analytics-mcp-http
# or
python -m analytics_mcp.server_http
```

The MCP endpoint will be available at `http://localhost:8000/mcp`.

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
