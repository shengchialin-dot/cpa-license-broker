# CPA License Broker（FastAPI）部署指引

## 專案內容
- `broker_server_fastapi.py`：FastAPI 伺服器（端點：`POST /license`、`GET /healthz`）
- `requirements.txt`：套件
- `Procfile`、`runtime.txt`：Heroku 使用
- `render.yaml`：Render 使用
- `railway.json`：Railway 使用
- `Dockerfile`：容器部署

## 環境變數
- `ALLOWLIST`：以逗號分隔的 `device_id`（例如 `"abc...,def..."`）
- `DEFAULT_PLAN`：不在 allowlist 的裝置預設方案（FREE/PRO）
- `DEFAULT_EXPIRE`：回傳給客戶端的授權到期日（字串 `YYYY-MM-DD`）
- `TTL_SECONDS`：授權回應有效秒數（預設 1800 = 30 分鐘）

## Render 部署
1. 登入 Render → New + → Blueprint（使用本資料夾的 `render.yaml`）。
2. 接上 Git（建議把這個資料夾推到你的 Repo）。
3. 部署後在「環境變數」設定 `ALLOWLIST` 等。
4. 取得 Web Service 的 URL，例如：`https://cpa-license-broker.onrender.com/license`

## Railway 部署
1. 建立新專案 → 部署此資料夾（或連 Git）。
2. Railway 會讀取 `railway.json` 自動建置。
3. 在 Variables 設 `ALLOWLIST` 等。
4. 取得服務 URL。

## Heroku 部署
```bash
heroku create cpa-license-broker
heroku buildpacks:add heroku/python
git push heroku main   # 或指定分支
heroku config:set ALLOWLIST="abc...,def..." DEFAULT_PLAN="FREE" DEFAULT_EXPIRE="2099-12-31" TTL_SECONDS="1800"
heroku ps:scale web=1
heroku open
```
> Heroku 上會自動使用 `Procfile` 與 `runtime.txt`。

## Docker
```bash
docker build -t cpa-broker .
docker run -p 8000:8000 -e ALLOWLIST="abc...,def..." cpa-broker
# 然後打 http://localhost:8000/license
```

## 客戶端設定
在執行你的工具（Broker API 客戶端版）前：
- 設定環境變數 `API_URL` 為你部署後的 `/license` 完整 URL。
  - Windows：`set API_URL=https://<your-host>/license`
  - Mac/Linux：`export API_URL=https://<your-host>/license`

## 取得 device_id（加入 allowlist）
- 執行工具 → 右上【關於/授權】可看到裝置 ID（前後 8 碼）。
- 你也可以請使用者回報完整的 `device_id`（40 字節十六進位字串）。
- 把它加入 `ALLOWLIST`，數分鐘內生效（端視平台）。
