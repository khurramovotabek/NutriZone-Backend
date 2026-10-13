# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Base: shared system dependencies for development and production
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root application user
RUN groupadd --gid 1000 nutrizone && \
    useradd \
        --uid 1000 \
        --gid nutrizone \
        --shell /bin/bash \
        --create-home \
        nutrizone

WORKDIR /app


# ---------------------------------------------------------------------------
# Builder: build Python wheels
# Keeps build dependencies out of final images
# ---------------------------------------------------------------------------
FROM base AS builder

# Build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definitions
COPY requirements/ requirements/

ARG REQUIREMENTS_FILE=production.txt

# Build wheels
RUN pip wheel \
        --wheel-dir=/wheels \
        -r requirements/${REQUIREMENTS_FILE}


# ---------------------------------------------------------------------------
# Development image
# ---------------------------------------------------------------------------
FROM base AS development

# Install pre-built wheels
COPY --from=builder /wheels /wheels
COPY requirements/ requirements/
#
# Real, closed gap: requirements/development.txt now pulls in
# requirements/testing.txt itself (`-r testing.txt`), so the single
# `pip wheel` call in the builder stage (REQUIREMENTS_FILE=
# development.txt, per docker-compose.yml's build args) already
# builds wheels for pytest/pytest-django/lupa/daphne/etc, and this one
# `--no-index` install below is enough to get all of them, including
# lupa's compiled C extension (built with the builder stage's own
# build-essential, never needed in this final stage). Previously this
# was two separate installs, the second (`-r testing.txt`) silently
# swallowed with `|| true` because no wheel for it ever existed --
# every testing dependency, `pytest` included, was silently absent
# from every development image ever built from this Dockerfile.
RUN pip install \
        --no-index \
        --find-links=/wheels \
        -r requirements/development.txt

# Copy application source
COPY . .

# Create runtime directories before switching to non-root user.
# Django logging uses /app/logs/api.log.
RUN mkdir -p /app/logs \
    && chown -R nutrizone:nutrizone /app

# Copy entrypoint scripts
COPY docker/django/entrypoint.sh /entrypoint.sh
COPY docker/django/migrate-entrypoint.sh /migrate-entrypoint.sh

# Make entrypoint scripts executable
RUN chmod +x \
        /entrypoint.sh \
        /migrate-entrypoint.sh

# Run application as non-root user
USER nutrizone

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


# ---------------------------------------------------------------------------
# Production image
# ---------------------------------------------------------------------------
FROM base AS production

# Install pre-built wheels
COPY --from=builder /wheels /wheels
COPY requirements/ requirements/

RUN pip install \
        --no-index \
        --find-links=/wheels \
        -r requirements/production.txt

# Copy application source
COPY . .

# Create runtime directories before switching to non-root user.
# Django logging uses /app/logs/api.log; /app/static and /app/media are the mount points of the static/media
# volumes (docker-compose.prod.yml) -- created here so a fresh named volume inherits nutrizone's ownership.
RUN mkdir -p /app/logs /app/static /app/media \
    && chown -R nutrizone:nutrizone /app

# Copy entrypoint scripts
COPY docker/django/entrypoint.sh /entrypoint.sh
COPY docker/django/migrate-entrypoint.sh /migrate-entrypoint.sh

# Make entrypoint scripts executable
RUN chmod +x \
        /entrypoint.sh \
        /migrate-entrypoint.sh

# Run application as non-root user
USER nutrizone

EXPOSE 8000

# Production health check
HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", "config.asgi:application", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "60", "--forwarded-allow-ips", "*"]
