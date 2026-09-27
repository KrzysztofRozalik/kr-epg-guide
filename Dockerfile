FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KR_EPG_CONFIG=/app/config.yaml

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --upgrade pip && pip install .

COPY config.example.yaml /app/config.yaml
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/output /app/state \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8080

CMD ["uvicorn", "kr_live_epg.service:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
