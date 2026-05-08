# ── 백엔드 Dockerfile (FastAPI) ──────────────────────────
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 복사 (레이어 캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# --timeout-graceful-shutdown: 리로드 시 hanging 태스크(외부 API 호출 등)를
# 최대 5초 후 강제 종료해 "Waiting for background tasks" 데드락 방지
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--timeout-graceful-shutdown", "5"]
