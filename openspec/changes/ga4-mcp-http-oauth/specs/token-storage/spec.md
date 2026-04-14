## ADDED Requirements

### Requirement: 抽象化 TokenStore 介面
系統 SHALL 定義 `TokenStore` 抽象基底類別（ABC），包含 `get`、`set`、`delete` 三個非同步方法，讓使用者可自行實作不同的儲存後端。

#### Scenario: 自訂後端實作
- **WHEN** 使用者繼承 `TokenStore` 並實作三個方法
- **THEN** 可直接替換 `GCSTokenStore` 注入 server，無需修改其他程式碼

### Requirement: GCS 預設實作（`GCSTokenStore`）
系統 SHALL 提供 `GCSTokenStore` 作為預設實作，將 token 資料以 Fernet 加密後存入 GCS private bucket。

#### Scenario: Token 寫入 GCS
- **WHEN** 使用者完成 OAuth 授權
- **THEN** `{access_token, refresh_token, token_expiry, user_email}` 以 Fernet 加密後，寫入 `gs://{GCS_BUCKET_NAME}/tokens/{google_user_id}.enc`

#### Scenario: Token 讀取 GCS
- **WHEN** 工具執行時需要使用者 credentials
- **THEN** 從 GCS 讀取對應 blob，以 Fernet 解密後回傳 token 資料

#### Scenario: 使用者不存在
- **WHEN** 查詢一個從未登入的 user_id
- **THEN** `get()` 回傳 `None`，不拋出例外

#### Scenario: GCS Bucket 設定錯誤
- **WHEN** `GCS_BUCKET_NAME` 環境變數指向不存在的 bucket
- **THEN** 初始化時拋出明確錯誤訊息

### Requirement: Token 加密
所有存入 TokenStore 的 token 資料 SHALL 以 Fernet 對稱加密（`TOKEN_ENCRYPTION_KEY` 環境變數），GCS bucket 本身亦啟用 at-rest 加密。

#### Scenario: 加密 key 正確
- **WHEN** `TOKEN_ENCRYPTION_KEY` 為有效的 Fernet key
- **THEN** token 正確加密並可解密

#### Scenario: 加密 key 缺失
- **WHEN** `TOKEN_ENCRYPTION_KEY` 環境變數未設定
- **THEN** server 啟動時拋出明確錯誤，不繼續執行

### Requirement: Token 自動 Refresh
`GCSTokenStore.get()` SHALL 在 access token 過期時，自動使用 refresh token 向 Google Token Endpoint 取得新的 access token，並將更新後的 token 寫回 GCS。

#### Scenario: Access token 過期
- **WHEN** 讀取 token 時發現 `token_expiry` 已過
- **THEN** 使用 `refresh_token` 呼叫 Google Token Endpoint，取得新的 `access_token` 與 `token_expiry`，更新 GCS 後回傳新 token

#### Scenario: Refresh token 失效
- **WHEN** 使用 refresh token 時 Google 回傳 `invalid_grant`
- **THEN** 刪除該使用者的 token 記錄，並回傳 `None`，讓使用者重新走 OAuth flow
