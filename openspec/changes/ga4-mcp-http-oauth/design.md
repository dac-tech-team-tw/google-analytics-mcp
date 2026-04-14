## Context

Google Analytics MCP 目前以 stdio transport 運作，每位使用者需在本機安裝 Python 環境與 gcloud CLI，並手動設定 Application Default Credentials。廣告代理商有 40 位分析師需要使用 GA4 MCP，這樣的安裝負擔不切實際。

目標是部署一個共用的 HTTP MCP Server 到 GCP Cloud Run，讓分析師只需透過 Google 帳號登入即可使用，無需任何本機安裝。

此 Repo 為 fork 自 Google 官方的 open source 專案，會公開於 GitHub，因此設計必須具備通用性，讓社群也能自行部署。

**技術棧選擇**：FastMCP（Python）—— 原有 codebase 已使用 Python，FastMCP 提供 HTTP transport 與 GoogleProvider 原生支援，遷移成本最低。

---

## Goals / Non-Goals

**Goals:**
- 將 server 改為 FastMCP HTTP Streamable transport，部署至 Cloud Run
- 整合 Google OAuth 2.0，使用者以 Google 帳號授權（含 `analytics.readonly` scope）
- 實作抽象化 `TokenStore` 介面，GCS 為預設實作，其他使用者可自行替換後端
- 每個 MCP 請求使用該使用者的 Google credentials 呼叫 GA4 API（per-user credentials）
- 所有設定透過環境變數注入，敏感資訊建議存放 Secret Manager
- 保持 open source 友善：提供 `.env.example`、清楚的部署文件

**Non-Goals:**
- 支援非 Google 的 IdP（Okta、Azure AD 等）
- 實作 GA4 write 操作（維持 read-only）
- 多租戶隔離（所有使用者共用同一 Cloud Run instance）
- 自動 token rotation 以外的使用者管理介面

---

## Decisions

### 決策 1：使用 FastMCP 取代原有 mcp SDK

**選擇**：用 `fastmcp` 套件完全取代 `mcp.server.stdio`

**理由**：FastMCP 提供 HTTP transport、GoogleProvider、Lifespan management 等開箱即用功能，若繼續用低階 SDK 需要自行實作這些。遷移成本低，因為原有 `@mcp.tool` 裝飾器寫法幾乎相同。

**備選方案**：繼續用低階 MCP SDK 自行接 Starlette —— 工作量大，維護負擔高，不採用。

---

### 決策 2：使用 FastMCP GoogleProvider 處理 OAuth

**選擇**：`fastmcp.server.auth.providers.google.GoogleProvider`

**理由**：GoogleProvider 已內建 OAuth 2.0 flow（redirect、callback、token 驗證）、JWT session 管理、token storage 介面。不需自行實作整個 OAuth server。

**關鍵細節**：`required_scopes` 必須包含 `https://www.googleapis.com/auth/analytics.readonly`，讓 OAuth flow 同時取得 GA4 的授權。Google 會在使用者同意後回傳含此 scope 的 access token。

**備選方案**：自行實作 OAuth server（如 Authlib）—— 複雜度過高，且 FastMCP 已整合好，不採用。

---

### 決策 3：不需要自訂 Token Storage（實際驗證後修訂）

**原始設計**：定義 `TokenStore` ABC，提供 `GCSTokenStore` 實作，將 Google tokens 存至 GCS。

**實際行為（整合測試後發現）**：FastMCP 的 `GoogleProvider` 本身就是 OAuth Proxy，它在內部持有 refresh token，並在每次請求時向 MCP client 傳遞有效的 Google access token 作為 Bearer token。

因此 GCS token 儲存層、Fernet 加密、`TokenStore` ABC 全數不需要，已從 codebase 移除。

**依賴清理**：`google-cloud-storage`、`cryptography`、`google-auth-oauthlib` 從 `pyproject.toml` 移除。

**需要的環境變數**（比原設計少）：
- `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`（OAuth App）
- `BASE_URL`（Cloud Run 服務 URL）
- `JWT_SIGNING_KEY`（FastMCP session token 簽章）

---

### 決策 4：Per-user credentials 直接從 Bearer token 取得（實際驗證後修訂）

**原始設計**：透過 `user_id` 查 `TokenStore` 取得儲存的 Google credentials。

**實際實作**：`get_access_token().token` 本身即為有效的 Google access token，直接建立 credentials 物件即可，無需任何二次儲存或查詢。

```python
# _with_user_credentials wrapper（server_http.py）
token = get_access_token()          # FastMCP 驗證後的 access token
google_access_token = token.token   # 即 Google access token（ya29.xxx）
credentials = google.oauth2.credentials.Credentials(
    token=google_access_token
)
# 設進 contextvar，所有 create_*_api_client() 自動取用
ctx_token = _current_credentials.set(credentials)
```

**Token refresh**：FastMCP 的 `GoogleProvider` 使用 `access_type=offline` + `prompt=consent` 取得 refresh token，並在 token 過期時自動刷新，對應用層完全透明。

**備選方案**：共用 Service Account —— 無法區分各使用者的 GA4 存取權，不採用。

---

### 決策 5：Cloud Run 部署，Port 由環境變數控制

**選擇**：Dockerfile + `PORT` 環境變數（Cloud Run 標準）

```python
mcp.run(transport="http", port=int(os.environ.get("PORT", 8000)))
```

**理由**：Cloud Run 自動注入 `PORT`，無需額外設定。Stateless 的 HTTP transport 天然適合 Cloud Run 的水平擴展。

---

## Risks / Trade-offs

**[已解決] Google access token 過期（1 小時）**
→ FastMCP 的 `GoogleProvider` 以 `access_type=offline` 取得 refresh token，token 過期時由 FastMCP 自動刷新，應用層無需處理。

**[已解決] FastMCP GoogleProvider 的 token storage 整合**
→ 整合測試後確認 `GoogleProvider` 本身即為 OAuth Proxy，每次 request 的 Bearer token 就是有效的 Google access token，不需要自訂 token storage。GCS 方案已移除。

**[已消除] GCS 延遲 vs Redis**
→ 由於不再使用 GCS 儲存 token，此 trade-off 不復存在。每次工具呼叫不需額外 I/O。

**[風險] FastMCP client_storage 預設儲存位置**
→ FastMCP `GoogleProvider` 的 `client_storage` 預設使用 `platformdirs` 的本機檔案系統。Cloud Run 為 stateless ephemeral container，重啟後會遺失。但這只影響 MCP client 的 OAuth 狀態（需重新登入），不影響資料正確性。可在未來傳入 `client_storage` 參數使用持久化後端解決。

---

## Migration Plan

1. **本機開發驗證**：在 local 以 `fastmcp dev` 測試 HTTP transport + GoogleProvider，確認 OAuth flow 正常
2. **GCS bucket 建立**：建立 private bucket，設定 Cloud Run SA 的 `storage.objectAdmin` 權限
3. **Secret Manager 設定**：存入 `GOOGLE_CLIENT_SECRET`、`TOKEN_ENCRYPTION_KEY`、`JWT_SIGNING_KEY`
4. **Cloud Run 部署**：`gcloud run deploy`，設定環境變數與 Secret Manager references
5. **Google OAuth Client 設定**：在 Google Cloud Console 新增 Cloud Run URL 到 Authorized redirect URIs
6. **灰度測試**：先開放 5 位分析師測試，確認正常後全面推廣

**Rollback**：舊的 stdio server 仍可透過 `python -m analytics_mcp.server --transport stdio` 啟動，Cloud Run 可直接 redeploy 舊版 image。

---

## Open Questions

1. FastMCP `GoogleProvider` 的 `client_storage` 是否接受自訂的 key-value 介面？需查閱原始碼確認，或是否需要另行實作 GA4 access token 的獨立儲存層
2. Cloud Run 是否需要 VPC connector（若 GCS 需要 private access）？一般情況下 Cloud Run 可直接存取 GCS，應不需要
3. 是否需要支援 `analytics.edit` scope 供未來寫入操作？初版維持 read-only，預留擴充空間
