# broker_server_fastapi.py
"""
最小授權 Broker（FastAPI）：不暴露 OneDrive 連結
- 以簡單 allowlist 綁定 device_id（逗號分隔的環境變數 ALLOWLIST）
- 回傳 plan/expire 與短效 ttl_seconds
部署方式：Render / Railway / Heroku / Docker 皆可
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time, os

app = FastAPI()

# 環境變數
ALLOWLIST = set(os.environ.get("ALLOWLIST", "").split(",")) if os.environ.get("ALLOWLIST") else set()
DEFAULT_PLAN = os.environ.get("DEFAULT_PLAN", "FREE").upper()
DEFAULT_EXPIRE = os.environ.get("DEFAULT_EXPIRE", "2099-12-31")
TTL_SECONDS = int(os.environ.get("TTL_SECONDS", "1800"))  # 30 分鐘

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/license")
async def license_endpoint(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    device_id = str(body.get("device_id", ""))
    app_ver = str(body.get("app_ver", ""))

    plan = "PRO" if device_id in ALLOWLIST else DEFAULT_PLAN

    return JSONResponse({
        "plan": plan,
        "expire": DEFAULT_EXPIRE,
        "user_upn": None,
        "ttl_seconds": TTL_SECONDS,
        "server_ts": int(time.time()),
        "app_ver": app_ver or None,
    })
