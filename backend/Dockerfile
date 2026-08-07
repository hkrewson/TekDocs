# syntax=docker/dockerfile:1.7
FROM python:3.13-alpine3.23 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apk add --no-cache \
      curl \
      libffi \
      libjpeg-turbo \
      openjpeg

RUN addgroup --system --gid 10001 tekdocs \
    && adduser --system --uid 10001 --ingroup tekdocs --home /app tekdocs

WORKDIR /app
COPY pyproject.toml ./
COPY apps ./apps
COPY tekdocs ./tekdocs
RUN pip install .
COPY manage.py ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0555 /entrypoint.sh \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R tekdocs:tekdocs /app

FROM base AS development
USER root
RUN pip install '.[dev]'
USER tekdocs
ENTRYPOINT ["/entrypoint.sh"]

FROM base AS production
USER tekdocs
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-", "tekdocs.wsgi:application"]
