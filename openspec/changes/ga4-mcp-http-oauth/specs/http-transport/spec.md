## ADDED Requirements

### Requirement: Server 以 HTTP Streamable transport 啟動
Server SHALL 使用 FastMCP HTTP Streamable transport 啟動，監聽由 `PORT` 環境變數指定的 port（預設 8000），取代原有 stdio transport。

#### Scenario: 正常啟動
- **WHEN** 執行 `python -m analytics_mcp.server`（或 `uvicorn`）
- **THEN** Server 在指定 port 監聽 HTTP 請求，MCP endpoint 為 `/mcp`

#### Scenario: PORT 環境變數覆蓋
- **WHEN** 設定環境變數 `PORT=9000`
- **THEN** Server 監聽 port 9000

### Requirement: 支援多個 MCP Client 同時連線
Server SHALL 支援多個 MCP client 同時透過 HTTP 連線，不同 session 之間互相隔離。

#### Scenario: 多 client 同時請求
- **WHEN** 兩個 MCP client 同時送出不同工具請求
- **THEN** 兩個請求均正確回應，不互相干擾

### Requirement: Cloud Run 相容
Server SHALL 在 GCP Cloud Run 環境中正常運作，支援無狀態水平擴展。

#### Scenario: Cloud Run 健康檢查
- **WHEN** Cloud Run 對 `/` 或指定 health check path 發送 GET 請求
- **THEN** Server 回應 200 OK

#### Scenario: 無狀態請求處理
- **WHEN** 同一使用者的兩個連續請求由不同 Cloud Run instance 處理
- **THEN** 兩個請求均能正確取得該使用者的 credentials 並完成 GA4 API 呼叫
