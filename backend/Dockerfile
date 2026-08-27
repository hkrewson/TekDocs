# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM python:3.13-alpine3.23@sha256:7ea3f82de8ea6d4fb7e5d2bbe3fe3c9d931700b7a529f1fe5769e42abe514ca1 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apk upgrade --no-cache \
    && apk add --no-cache \
      curl \
      libffi \
      libjpeg-turbo \
      openjpeg

RUN addgroup --system --gid 10001 tekdocs \
    && adduser --system --uid 10001 --ingroup tekdocs --home /app tekdocs

WORKDIR /app
COPY pyproject.toml build-requirements.lock requirements.lock requirements-dev.lock ./
RUN pip install --require-hashes -r build-requirements.lock \
    && pip install --require-hashes -r requirements.lock
COPY apps ./apps
COPY tekdocs ./tekdocs
RUN pip install --no-build-isolation --no-deps .
COPY manage.py ./
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/migrate.sh /migrate.sh
RUN chmod 0555 /entrypoint.sh \
    && chmod 0555 /migrate.sh \
    && mkdir -p /app/staticfiles /app/media /app/diagram-jobs \
    && chown -R tekdocs:tekdocs /app

FROM base AS development
ENV TEKDOCS_IMAGE_VARIANT=development
USER root
RUN pip install --require-hashes -r requirements-dev.lock
USER tekdocs
ENTRYPOINT ["/entrypoint.sh"]

FROM base AS production
ENV TEKDOCS_IMAGE_VARIANT=production
USER root
# Build tooling is not part of the application runtime. Removing it also keeps
# pip's independently versioned vendored libraries out of the shipped image.
RUN python -m pip uninstall --yes pip setuptools wheel
USER tekdocs
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-", "tekdocs.wsgi:application"]
