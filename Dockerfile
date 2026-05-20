# ── Build ──
FROM python:3.12-slim AS builder

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir uv && \
    uv build --wheel

# ── Runtime ──
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/open-webui/oikb"
LABEL org.opencontainers.image.description="CLI tool for syncing content to Open WebUI Knowledge Bases"

# Install oikb from the built wheel.
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Sync source is mounted at /data by convention.
VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["oikb"]
