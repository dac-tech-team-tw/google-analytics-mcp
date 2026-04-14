# Google Analytics MCP Server

> **This is a fork of [googleanalytics/google-analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp).**
>
> The original project runs as a local stdio MCP server that requires each user to install Python and configure Google credentials on their own machine. This fork adds an **HTTP Streamable MCP server with Google OAuth**, deployable to GCP Cloud Run, so teams can share a single server without any local setup.

## What's Different in This Fork

| | Original | This Fork |
|---|---|---|
| Transport | stdio (local only) | HTTP Streamable (Cloud Run) |
| Authentication | Application Default Credentials (per machine) | Google OAuth 2.0 (per user, browser login) |
| Deployment | Local process | GCP Cloud Run |
| Multi-user | Each user runs their own server | Single shared server for the whole team |

**New entry point**: `analytics-mcp-http`

**New files**:
- `analytics_mcp/server_http.py` — FastMCP HTTP server with GoogleProvider
- `analytics_mcp/auth_provider.py` — GoogleProvider configuration
- `Dockerfile` — Cloud Run container
- `docs/quickstart.md` — Deployment guide

The original `analytics-mcp` stdio entry point is preserved and unchanged.

---

## Tools

The server provides the same GA4 tools as the original, using the
[Google Analytics Admin API](https://developers.google.com/analytics/devguides/config/admin/v1)
and
[Google Analytics Data API](https://developers.google.com/analytics/devguides/reporting/data/v1).

### Account & property information

- `get_account_summaries` — List all GA4 accounts and properties the user has access to
- `get_property_details` — Get details for a specific property
- `list_google_ads_links` — List Google Ads links for a property
- `list_property_annotations` — List annotations for a property

### Reports

- `run_report` — Run a GA4 Data API report
- `get_custom_dimensions_and_metrics` — List custom dimensions and metrics for a property

### Realtime

- `run_realtime_report` — Run a GA4 realtime report

---

## Deployment (HTTP / Cloud Run mode)

See **[docs/quickstart.md](docs/quickstart.md)** for the full Cloud Run deployment guide.

The short version:

1. Create a Google OAuth 2.0 Client ID (Web application)
2. Deploy the Docker image to Cloud Run with 4 environment variables
3. Connect your MCP client to `https://<your-service>.run.app/mcp`

---

## Local stdio mode (original)

The original stdio setup still works. Follow the
[original instructions](https://github.com/googleanalytics/google-analytics-mcp#setup-instructions-)
or configure your MCP client with:

```json
{
  "mcpServers": {
    "analytics-mcp": {
      "command": "pipx",
      "args": ["run", "analytics-mcp"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "PATH_TO_CREDENTIALS_JSON"
      }
    }
  }
}
```

---

## Sample Prompts

- `What GA4 properties do I have access to?`
- `Give me the pageviews for /zh-tw/benefit/ on 2026-04-01`
- `What are the top 10 pages by sessions in the last 30 days?`
- `What are the custom dimensions in property 274215129?`
- `Show me realtime active users right now`

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

Upstream changes from [googleanalytics/google-analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp) can be merged via standard git upstream workflow.
