FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-deploy.txt ./
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements-deploy.txt

COPY backend ./backend
COPY rag ./rag
COPY eligibility ./eligibility
COPY rules ./rules

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
