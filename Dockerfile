FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY broker_server_fastapi.py /app/

# 環境變數（可在部署時覆蓋）
ENV ALLOWLIST=""
ENV DEFAULT_PLAN="FREE"
ENV DEFAULT_EXPIRE="2099-12-31"
ENV TTL_SECONDS="1800"

EXPOSE 8000
CMD ["uvicorn", "broker_server_fastapi:app", "--host", "0.0.0.0", "--port", "8000"]
