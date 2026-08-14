# Revision Prompt 16, task: Dockerfiles + docker-compose + deployment
# docs. Multi-stage build using `uv` (this project's actual dependency
# manager, per pyproject.toml) rather than falling back to plain pip —
# `uv sync --frozen` installs exactly what `uv.lock` pins, the same
# dependency set local dev and CI use.

FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/
WORKDIR /app
# UV_PYTHON_DOWNLOADS=never: this base image already ships the exact
# Python `uv sync` needs, so there is no reason for it to reach out to
# astral-sh/python-build-standalone's GitHub releases for a managed
# interpreter during the build — that outbound fetch is both
# unnecessary and a real source of build flakiness on hosts with
# unreliable egress to GitHub's release CDN (seen failing on Railway's
# builder with an http2 "refused stream" error).
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Dependencies first, cached separately from the source copy below so an
# app code change doesn't invalidate the (slow) dependency-install layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.14-slim AS runtime
WORKDIR /app
RUN useradd --create-home --shell /bin/bash appuser
COPY --from=builder --chown=appuser:appuser /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser

EXPOSE 8000
ENV PORT=8000
# Shell-form CMD (not exec-form) so $PORT is actually expanded — hosts
# like Railway inject their own PORT at container runtime, which
# silently overrides this ENV default and previously caused the fixed
# `--port 8000` below to listen on the wrong port entirely (the host's
# edge proxy would route to its expected port and get nothing, a
# platform-level "Application failed to respond", not an app crash).
# `apps/web/Dockerfile`'s Next.js server already reads $PORT itself;
# this makes the api container equally portable across hosts.
#
# HEALTHCHECK deliberately removed (temporary, per Railway support
# troubleshooting a live "Application failed to respond" case,
# 2026-08-13/14): testing whether Railway's own routing treats a
# Docker-level HEALTHCHECK's status as a gate on whether to route
# traffic to the container at all, independent of Railway's own
# platform-level health checks. Re-add once confirmed either way.

CMD uvicorn tradingos_api.main:app --host 0.0.0.0 --port "$PORT"
