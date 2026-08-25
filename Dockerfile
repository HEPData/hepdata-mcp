# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md CHANGELOG.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

RUN useradd --create-home --home-dir /home/hepdata --shell /usr/sbin/nologin hepdata

WORKDIR /app

COPY --from=builder --chown=hepdata:hepdata /app/.venv /app/.venv

USER hepdata

EXPOSE 8000

ENTRYPOINT ["hepdata-mcp"]
CMD []
