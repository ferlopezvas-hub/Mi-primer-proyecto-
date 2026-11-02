ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
# Rol del contenedor: api | worker | beat | migrate
ENV ROLE=api
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD [ "$ROLE" != "api" ] || curl -fsS http://localhost:8000/health/live || exit 1
CMD ["sh", "scripts/entrypoint.sh"]
