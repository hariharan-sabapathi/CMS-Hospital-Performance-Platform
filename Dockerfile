# syntax=docker/dockerfile:1

# --- builder: install deps into a venv --------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --target=/build/deps .

# --- runtime: minimal image, non-root user -----------------------------------
FROM python:3.11-slim AS runtime

RUN groupadd --gid 1000 cms && useradd --uid 1000 --gid cms --create-home cms

WORKDIR /app
COPY --from=builder /build/deps /usr/local/lib/python3.11/site-packages
COPY src/ ./src/
COPY dbt/ ./dbt/
COPY data/ ./data/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

USER cms
EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "cms_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
