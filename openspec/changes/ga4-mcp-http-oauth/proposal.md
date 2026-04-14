## Why

目前 GA4 MCP Server 僅支援 stdio transport，每位使用者都需要在本機安裝 Python、pipx 套件以及 gcloud CLI 並手動設定 Application Default Credentials，導致 40+ 位分析師的導入成本極高。將 Server 改為 HTTP Streamable 並整合 Google OAuth，可部署至 GCP Cloud Run，讓所有人共用同一個端點，大幅降低維運與導入複雜度。

## What Changes

- **新增** HTTP Streamable transport，取代現有 stdio transport
- **新增** Google OAuth 2.0 登入流程（透過 FastMCP `GoogleProvider`），使用者直接以 Google 帳號授權，無需 gcloud CLI
- **新增** 抽象化 Token Storage 介面（`TokenStore` ABC），預設提供 GCS 實作（Fernet 加密）
- **新增** Per-user credentials 機制：每個 MCP 請求使用該使用者自己的 Google access token 呼叫 GA4 API
- **修改** `analytics_mcp/tools/utils.py`：`_create_credentials()` 從 session token 取得使用者 credentials，取代 Application Default Credentials
- **修改** `analytics_mcp/server.py`：改用 FastMCP + HTTP transport 啟動，整合 GoogleProvider
- **新增** Cloud Run 部署支援（Dockerfile、`PORT` 環境變數）
- **BREAKING** stdio 模式不再是預設啟動方式，改為 HTTP transport

## Capabilities

### New Capabilities

- `http-transport`: 以 FastMCP HTTP Streamable transport 取代 stdio，支援多使用者同時連線
- `google-oauth`: 整合 Google OAuth 2.0 登入流程，使用者以 Google 帳號授權並取得 `analytics.readonly` scope
- `token-storage`: 抽象化 token 儲存介面，提供 GCS 加密實作，可由其他使用者自行替換後端（Redis、Firestore 等）
- `per-user-credentials`: 每個 MCP 請求使用該使用者的 Google credentials 呼叫 GA4 API，而非共用的 ADC

### Modified Capabilities

（無既有 spec 需要修改）

## Impact

- **程式碼**: `server.py`、`coordinator.py`、`tools/utils.py` 需修改；新增 `analytics_mcp/storage/` 模組、`analytics_mcp/auth.py`
- **依賴套件**: 新增 `fastmcp`、`google-cloud-storage`、`cryptography`；移除直接使用 `mcp.server.stdio`
- **部署**: 需要 GCP Cloud Run、GCS bucket、Google OAuth 2.0 Client（Web application 類型）
- **環境變數**: `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`BASE_URL`、`GCS_BUCKET_NAME`、`TOKEN_ENCRYPTION_KEY`、`JWT_SIGNING_KEY`
- **安全性**: Token 以 Fernet 加密後存入 GCS private bucket，Cloud Run SA 持有最小權限
- **相容性**: 現有 stdio 用法可透過 CLI flag 或環境變數保留，但 HTTP 為預設模式
