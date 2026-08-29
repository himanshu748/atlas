# ATLAS — single-container deploy for Cloud Run.
# One image serves the API, the SSE stream and the console UI.

FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Dependencies first so layer caching survives source edits. The Linux/Python
# 3.12 graph is fully pinned and hash-checked for reproducible cloud builds.
COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock

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
