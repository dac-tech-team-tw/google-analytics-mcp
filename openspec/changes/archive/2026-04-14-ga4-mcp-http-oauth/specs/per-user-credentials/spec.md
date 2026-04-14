## ADDED Requirements

### Requirement: 每個 MCP 請求使用該使用者的 Google Credentials
所有 GA4 API 呼叫 SHALL 使用發出請求的使用者自己的 Google access token，而非共用的 Service Account 或 Application Default Credentials。

#### Scenario: 工具執行時取得 per-user credentials
- **WHEN** 使用者呼叫任何 GA4 工具（如 `run_report`、`list_properties`）
- **THEN** Server 從 FastMCP session token 取出 `user_id`，向 `TokenStore` 查詢該使用者的 Google credentials，並使用這些 credentials 建立 GA4 API client

#### Scenario: 使用者無 GA4 存取權限
- **WHEN** 使用者的 Google 帳號對指定的 GA4 property 沒有 View 權限
- **THEN** GA4 API 回傳 403，工具回傳明確錯誤訊息（如 `Error: Permission denied. Your Google account does not have access to property {id}.`）

### Requirement: GA4 API Client 以 per-request credentials 建立
`tools/utils.py` 的 API client 建立函式 SHALL 接受 `google.auth.credentials.Credentials` 參數，而非內部呼叫 `google.auth.default()`。

#### Scenario: 傳入使用者 credentials
- **WHEN** 呼叫 `create_data_api_client(credentials=user_credentials)`
- **THEN** 回傳使用該使用者 credentials 的 `BetaAnalyticsDataAsyncClient`

#### Scenario: 未傳入 credentials（向下相容）
- **WHEN** 呼叫 `create_data_api_client()` 不傳 credentials（供 stdio 模式使用）
- **THEN** 退回使用 `google.auth.default()` 取得 ADC

### Requirement: Credentials 不跨 Session 共用
不同使用者的 credentials SHALL 完全隔離，一個使用者的 token 不得用於另一個使用者的 API 呼叫。

#### Scenario: 兩個使用者同時呼叫工具
- **WHEN** 使用者 A 與使用者 B 同時呼叫 `list_properties`
- **THEN** A 的請求使用 A 的 credentials，B 的請求使用 B 的 credentials，互不干擾

### Requirement: Token 不存在時回傳明確錯誤
若 `TokenStore.get()` 回傳 `None`（使用者從未登入或 refresh token 失效），工具 SHALL 回傳引導使用者重新授權的錯誤訊息。

#### Scenario: Token 不存在
- **WHEN** 工具執行時發現 `TokenStore.get()` 回傳 `None`
- **THEN** 回傳錯誤訊息 `Error: Authentication required. Please reconnect to re-authorize with Google.`
