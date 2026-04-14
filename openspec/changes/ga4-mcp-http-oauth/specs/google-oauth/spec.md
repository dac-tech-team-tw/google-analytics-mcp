## ADDED Requirements

### Requirement: Google OAuth 2.0 登入流程
Server SHALL 實作 Google OAuth 2.0 Authorization Code Flow，使用者透過 Google 帳號登入並授權存取 GA4 資料，無需 gcloud CLI 或 Application Default Credentials。

#### Scenario: 首次登入
- **WHEN** MCP client 首次連線至 server
- **THEN** Server 引導使用者前往 Google OAuth 同意頁面

#### Scenario: 授權成功
- **WHEN** 使用者在 Google 同意授權
- **THEN** Server 取得含 `analytics.readonly` scope 的 access token 與 refresh token，並建立 MCP session

#### Scenario: 使用者拒絕授權
- **WHEN** 使用者拒絕 Google OAuth 授權
- **THEN** Server 回傳適當的錯誤訊息，MCP session 不建立

### Requirement: 請求必要的 OAuth Scopes
OAuth flow SHALL 請求以下 scopes：
- `openid`
- `email`
- `profile`
- `https://www.googleapis.com/auth/analytics.readonly`

#### Scenario: Scope 包含 analytics.readonly
- **WHEN** OAuth flow 發起 authorization request
- **THEN** request 的 `scope` 參數包含 `https://www.googleapis.com/auth/analytics.readonly`

### Requirement: 已登入使用者不需重新授權
Server SHALL 快取使用者的 session token，已登入的使用者在 token 有效期間內不需重新走 OAuth flow。

#### Scenario: Token 有效期間內重新連線
- **WHEN** 已授權的使用者在 session 有效期內重新連線
- **THEN** 直接建立 MCP session，不需再次 Google 登入

### Requirement: OAuth Client 設定透過環境變數注入
GoogleProvider SHALL 從環境變數讀取 OAuth client credentials，不得 hardcode。

#### Scenario: 環境變數設定
- **WHEN** 設定 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`BASE_URL`
- **THEN** GoogleProvider 使用這些值初始化，OAuth redirect URI 為 `{BASE_URL}/auth/callback`
