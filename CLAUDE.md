# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用指令

```bash
pip install -e ".[dev]"   # 安裝含開發工具的套件
nox -s format             # 格式化（black，80字元限制）
nox -s lint               # 檢查格式
nox -s tests              # 執行測試（目前 Python 版本）
nox -s "tests-3.12"       # 執行特定 Python 版本測試
```

測試檔案命名規則：`*_test.py`，放在 `tests/` 目錄。

## 專案結構索引

| 路徑 | 內容 |
|------|------|
| `README.md` | 使用者設定與工具說明 |
| `CONTRIBUTING.md` | 開發貢獻指南、本地測試方式 |
| `pyproject.toml` | 套件設定、依賴版本、進入點 |
| `noxfile.py` | 測試/格式化自動化設定 |
| `analytics_mcp/server.py` | MCP server 進入點（`run_server`） |
| `analytics_mcp/coordinator.py` | 工具協調邏輯 |
| `analytics_mcp/tools/admin/info.py` | Admin API 工具（帳號、屬性資訊） |
| `analytics_mcp/tools/reporting/core.py` | Data API 報表工具 |
| `analytics_mcp/tools/reporting/realtime.py` | 即時報表工具 |
| `analytics_mcp/tools/reporting/metadata.py` | 自訂維度/指標查詢 |
| `analytics_mcp/tools/utils.py` | 共用工具函式 |
| `tests/utils_test.py` | 單元測試 |

## 架構說明

MCP server 透過 `analytics_mcp/server.py` 啟動，工具分為兩類：
- **Admin API**（`tools/admin/`）：帳號與屬性管理
- **Data API**（`tools/reporting/`）：報表、即時報表、metadata

認證使用 Google Application Default Credentials（ADC），需 `analytics.readonly` scope。
