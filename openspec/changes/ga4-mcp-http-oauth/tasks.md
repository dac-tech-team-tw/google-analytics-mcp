## 1. 依賴套件與專案設定

- [x] 1.1 在 `pyproject.toml` 新增 `fastmcp`、`google-cloud-storage`、`cryptography` 依賴
- [x] 1.2 移除或標記 `mcp.server.stdio` 相關依賴為可選
- [x] 1.3 建立 `.env.example`，列出所有必要環境變數（`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`BASE_URL`、`GCS_BUCKET_NAME`、`TOKEN_ENCRYPTION_KEY`、`JWT_SIGNING_KEY`）
- [x] 1.4 建立 `Dockerfile`，支援 Cloud Run 部署（`PORT` 環境變數、非 root 使用者）

## 2. Token Storage 模組

> **⚠️ 後來發現不需要** — FastMCP 的 `GoogleProvider` 本身即為 OAuth Proxy，
> 每次 tool call 時 Bearer token 就是有效的 Google access token，不需要自行管理 token 儲存。
> 下列任務雖已實作，但在整合測試後全數刪除（見 6.3）。

- [x] 2.1 建立 `analytics_mcp/storage/__init__.py`（已刪除）
- [x] 2.2 建立 `analytics_mcp/storage/base.py`，定義 `TokenStore` ABC（已刪除）
- [x] 2.3 建立 `analytics_mcp/storage/gcs.py`，實作 `GCSTokenStore`（已刪除）
- [x] 2.4 在 `GCSTokenStore.get()` 實作 token refresh 邏輯（已刪除）

## 3. Per-user Credentials 整合

- [x] 3.1 修改 `analytics_mcp/tools/utils.py`：
  - `create_data_api_client(credentials=None)` 接受可選 credentials 參數
  - `create_admin_api_client(credentials=None)` 接受可選 credentials 參數
  - `create_admin_alpha_api_client(credentials=None)` 接受可選 credentials 參數
  - 未傳入時退回 `google.auth.default()`（向下相容 stdio 模式）
- [x] 3.2 建立 `analytics_mcp/auth.py`，提供 `get_user_credentials(user_id: str) -> google.auth.credentials.Credentials | None` 輔助函式（整合測試後發現不需要，已刪除）
- [x] 3.3 修改所有工具函式（`tools/reporting/core.py`、`realtime.py`、`metadata.py`、`tools/admin/info.py`）：
  - 採用 `_with_user_credentials` wrapper 於 `server_http.py`，透過 contextvar 注入 credentials
  - 工具函式本身不需修改 signature（contextvar 在 `create_*_api_client()` 中自動讀取）

## 4. FastMCP Server 整合

- [x] 4.1 建立 `analytics_mcp/auth_provider.py`，設定 `GoogleProvider`：
  - 從環境變數讀取 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`BASE_URL`、`JWT_SIGNING_KEY`
  - `required_scopes` 包含 `openid`、`email`、`profile`、`https://www.googleapis.com/auth/analytics.readonly`
- [x] 4.2 建立 `analytics_mcp/server_http.py`（新檔案，原 server.py 保留 stdio 模式）：
  - 使用 `FastMCP` 整合 `GoogleProvider`
  - 啟動方式：`mcp.run(transport="http", port=int(os.environ.get("PORT", 8000)))`
  - 保留原有 stdio server.py 向下相容
- [x] 4.3 工具以 `_with_user_credentials` wrapper 包裝後掛載到 FastMCP（在 server_http.py 中）

## 5. GCP 基礎設施設定（文件）

- [x] 5.1 在 `docs/deployment.md` 撰寫 GCS bucket 建立步驟
- [x] 5.2 撰寫 Google Cloud Console 的 OAuth Client 設定步驟
- [x] 5.3 撰寫 Secret Manager 設定步驟
- [x] 5.4 撰寫 Cloud Run 部署指令與環境變數設定說明

## 6. 測試

- [x] 6.1 為 `GCSTokenStore` 撰寫單元測試（mock GCS client）
- [x] 6.2 為 `get_user_credentials()` 撰寫單元測試
- [x] 6.3 部署至 Cloud Run，以 Claude Code MCP client 驗證 OAuth flow 與 GA4 API 呼叫正常（整合測試通過）
- [x] 6.4 確認現有 `tests/utils_test.py` 測試在修改 `utils.py` 後仍通過（14/14 passed）
