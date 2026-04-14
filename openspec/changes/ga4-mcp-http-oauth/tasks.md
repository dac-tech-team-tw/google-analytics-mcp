## 1. 依賴套件與專案設定

- [ ] 1.1 在 `pyproject.toml` 新增 `fastmcp`、`google-cloud-storage`、`cryptography` 依賴
- [ ] 1.2 移除或標記 `mcp.server.stdio` 相關依賴為可選
- [ ] 1.3 建立 `.env.example`，列出所有必要環境變數（`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`BASE_URL`、`GCS_BUCKET_NAME`、`TOKEN_ENCRYPTION_KEY`、`JWT_SIGNING_KEY`）
- [ ] 1.4 建立 `Dockerfile`，支援 Cloud Run 部署（`PORT` 環境變數、非 root 使用者）

## 2. Token Storage 模組

- [ ] 2.1 建立 `analytics_mcp/storage/__init__.py`
- [ ] 2.2 建立 `analytics_mcp/storage/base.py`，定義 `TokenStore` ABC（`get`、`set`、`delete` 非同步方法）
- [ ] 2.3 建立 `analytics_mcp/storage/gcs.py`，實作 `GCSTokenStore`：
  - 從 `GCS_BUCKET_NAME`、`TOKEN_ENCRYPTION_KEY` 環境變數初始化
  - 路徑格式：`tokens/{google_user_id}.enc`
  - Fernet 加密 / 解密
  - `get()` 回傳 `None`（不存在時）
  - 啟動時驗證環境變數存在，否則拋出明確錯誤
- [ ] 2.4 在 `GCSTokenStore.get()` 實作 token refresh 邏輯：
  - 檢查 `token_expiry`，若過期使用 `refresh_token` 呼叫 Google Token Endpoint
  - 更新後寫回 GCS
  - 若 `invalid_grant`，刪除該使用者 token 並回傳 `None`

## 3. Per-user Credentials 整合

- [ ] 3.1 修改 `analytics_mcp/tools/utils.py`：
  - `create_data_api_client(credentials=None)` 接受可選 credentials 參數
  - `create_admin_api_client(credentials=None)` 接受可選 credentials 參數
  - `create_admin_alpha_api_client(credentials=None)` 接受可選 credentials 參數
  - 未傳入時退回 `google.auth.default()`（向下相容 stdio 模式）
- [ ] 3.2 建立 `analytics_mcp/auth.py`，提供 `get_user_credentials(user_id: str) -> google.auth.credentials.Credentials | None` 輔助函式，從 `TokenStore` 取得並建立 credentials 物件
- [ ] 3.3 修改所有工具函式（`tools/reporting/core.py`、`realtime.py`、`metadata.py`、`tools/admin/info.py`）：
  - 在工具開頭加入 `token = get_access_token(); user_id = token.claims["sub"]`
  - 呼叫 `get_user_credentials(user_id)` 取得 credentials
  - credentials 為 `None` 時回傳 `Error: Authentication required. Please reconnect to re-authorize with Google.`
  - 將 credentials 傳入 API client 建立函式

## 4. FastMCP Server 整合

- [ ] 4.1 建立 `analytics_mcp/auth_provider.py`，設定 `GoogleProvider`：
  - 從環境變數讀取 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`BASE_URL`、`JWT_SIGNING_KEY`
  - `required_scopes` 包含 `openid`、`email`、`profile`、`https://www.googleapis.com/auth/analytics.readonly`
  - 將 `GCSTokenStore` 傳入 `client_storage`（或確認橋接方式，參見 design.md Open Questions）
- [ ] 4.2 重寫 `analytics_mcp/server.py`：
  - 使用 `FastMCP` 取代 `mcp.server` 低階 SDK
  - 整合 `GoogleProvider` 至 `FastMCP(auth=auth_provider)`
  - 啟動方式：`mcp.run(transport="http", port=int(os.environ.get("PORT", 8000)))`
  - 保留 `--transport stdio` CLI flag 以向下相容
- [ ] 4.3 修改 `analytics_mcp/coordinator.py`：
  - 改用 `FastMCP` 裝飾器風格（`@mcp.tool`）取代原有工具註冊方式（若需要）
  - 確認所有工具正確掛載

## 5. GCP 基礎設施設定（文件）

- [ ] 5.1 在 `README.md` 或 `docs/deployment.md` 撰寫 GCS bucket 建立步驟：
  - 建立 private bucket，關閉 public access
  - 設定 Cloud Run SA 的 `roles/storage.objectAdmin` 權限
- [ ] 5.2 撰寫 Google Cloud Console 的 OAuth Client 設定步驟：
  - 應用類型：Web application
  - Authorized redirect URIs：`{BASE_URL}/auth/callback`
- [ ] 5.3 撰寫 Secret Manager 設定步驟（`GOOGLE_CLIENT_SECRET`、`TOKEN_ENCRYPTION_KEY`、`JWT_SIGNING_KEY`）
- [ ] 5.4 撰寫 Cloud Run 部署指令（`gcloud run deploy`）與環境變數設定說明

## 6. 測試

- [ ] 6.1 為 `GCSTokenStore` 撰寫單元測試（mock GCS client）：
  - `get()` 正常讀取
  - `get()` 不存在回傳 `None`
  - `set()` 正確加密寫入
  - `delete()` 刪除
  - Token refresh 邏輯（過期 → 呼叫 Google → 更新 GCS）
  - `invalid_grant` → 刪除 + 回傳 `None`
- [ ] 6.2 為 `get_user_credentials()` 撰寫單元測試
- [ ] 6.3 本機以 `fastmcp dev` 執行 HTTP transport 驗證 OAuth flow 是否正常（整合測試）
- [ ] 6.4 確認現有 `tests/utils_test.py` 測試在修改 `utils.py` 後仍通過（`nox -s tests`）
