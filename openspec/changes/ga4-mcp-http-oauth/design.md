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

### 決策 3：Token Storage 抽象化，預設 GCS 實作

**選擇**：定義 `TokenStore` ABC，提供 `GCSTokenStore` 實作

```
analytics_mcp/storage/
├── __init__.py
├── base.py      ← TokenStore ABC
└── gcs.py       ← GCSTokenStore（Fernet 加密）
```

**理由**：
- GCS 對 Cloud Run 友善，不需管理 Redis instance，成本低
- Token 讀寫僅發生在 OAuth flow 與 token refresh，不影響每次 API 呼叫效能
- 抽象介面讓社群可自行實作 Redis、Firestore、DynamoDB 等後端
- 40 人規模遠低於 GCS 的任何限制

**GCS 路徑設計**：`tokens/{google_user_id}.enc`（每人一個加密檔案）

**加密**：Fernet 對稱加密（`TOKEN_ENCRYPTION_KEY` 環境變數），GCS 本身另有 at-rest 加密

**備選方案**：Redis（Cloud Memorystore）—— 需 VPC 設定、固定費用、管理成本，對 40 人內部工具不划算，不採用。

---

### 決策 4：Per-user credentials 橋接機制

**選擇**：在 OAuth callback 時將 Google access token + refresh token 存入 `TokenStore`，工具執行時從 session 取出 `user_id` 再查 store 取得 credentials

```python
# 工具內取得 per-user credentials
token = get_access_token()          # FastMCP JWT session token
user_id = token.claims["sub"]       # Google user ID
stored = await token_store.get(user_id)
credentials = google.oauth2.credentials.Credentials(
    token=stored["access_token"],
    refresh_token=stored["refresh_token"],
    ...
)
client = data_v1beta.BetaAnalyticsDataAsyncClient(credentials=credentials)
```

**理由**：GA4 API 需要使用者的 Google access token（而非 FastMCP 內部的 JWT），兩者必須橋接。refresh token 確保 access token 過期後能自動更新，無需重新登入。

**備選方案**：共用 Service Account —— 無法區分各使用者的 GA4 存取權，且需為每個使用者額外設定 IAM，不採用。

---

### 決策 5：Cloud Run 部署，Port 由環境變數控制

**選擇**：Dockerfile + `PORT` 環境變數（Cloud Run 標準）

```python
mcp.run(transport="http", port=int(os.environ.get("PORT", 8000)))
```

**理由**：Cloud Run 自動注入 `PORT`，無需額外設定。Stateless 的 HTTP transport 天然適合 Cloud Run 的水平擴展。

---

## Risks / Trade-offs

**[風險] Google access token 過期（1 小時）**
→ 在 `GCSTokenStore.get()` 加入 token expiry 檢查，過期時使用 refresh token 呼叫 Google Token Endpoint 更新，並將新 token 寫回 GCS。

**[風險] FastMCP GoogleProvider 的 token storage 介面與自訂 `TokenStore` 的整合方式**
→ 需確認 `GoogleProvider` 的 `client_storage` 參數接受的介面，若不相容則需包裝 adapter。實作前須先驗證。

**[Trade-off] GCS 延遲 vs Redis**
→ 每次工具呼叫多一次 GCS 讀取（~50-100ms），對分析報表工具可接受。若未來有效能需求，可在 Lifespan 中加 in-memory cache（每個 Cloud Run instance 快取該 instance 服務的 tokens）。

**[風險] Cloud Run 多 instance 時 in-memory cache 不一致**
→ 初版不做 in-memory cache，直接讀 GCS，確保正確性。效能問題待量測後再優化。

**[風險] Fernet key 外洩**
→ 透過 Secret Manager 注入，不寫入環境變數明文。Cloud Run SA 的 Secret Manager accessor 權限最小化。

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
