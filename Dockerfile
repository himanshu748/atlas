# ATLAS — single-container deploy for Cloud Run.
# One image serves the API, the SSE stream and the console UI.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Dependencies first so layer caching survives source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY seed ./seed
COPY web ./web

# Non-root: Cloud Run does not require it, auditors do.
RUN useradd --create-home --uid 1001 atlas && chown -R atlas:atlas /app
USER atlas

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')" || exit 1

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 75
