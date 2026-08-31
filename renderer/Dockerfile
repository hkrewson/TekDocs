# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM node:26-alpine@sha256:aadf416b2cdce311a8811ba3f0608a61b77dbf997500e2eafe781b51f6a0b019

ENV NODE_ENV=production \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser \
    PUPPETEER_SKIP_DOWNLOAD=true

# Chromium comes from Alpine's repositories, which move independently of the pinned
# base image digest above. Left alone, the browser silently changes version between
# builds of the one service whose output is meant to be reproducible.
#
# The version is asserted rather than constrained: a constraint would quietly install an
# older browser when the repository moves, whereas this fails the build and asks for a
# deliberate decision. To bump, raise CHROMIUM_SERIES, rebuild, and re-run
# `make production-image-rehearsal`.
ARG CHROMIUM_SERIES=152

RUN apk upgrade --no-cache \
    && apk add --no-cache chromium rsvg-convert \
    && installed="$(/usr/bin/chromium-browser --version)" \
    && case "$installed" in \
         "Chromium ${CHROMIUM_SERIES}."*) : ;; \
         *) echo "Renderer expected Chromium ${CHROMIUM_SERIES}.x but Alpine provided: $installed" >&2; exit 1 ;; \
       esac \
    && printf '%s\n' "$installed" > /chromium-version \
    && chmod 0444 /chromium-version \
    && addgroup --system --gid 10001 renderer \
    && adduser --system --uid 10001 --ingroup renderer --home /renderer renderer

# `COPY --chmod` is stated on every copy below: Docker otherwise carries the source
# file's mode into the image, so a 0600 file on the build host becomes unreadable to
# the 10001 runtime user. The `chown` further down covers /renderer itself, not the
# files in it, so nothing else would repair that.
WORKDIR /renderer
COPY --chmod=0644 package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY --chmod=0644 check-licenses.mjs mermaid-config.json puppeteer-config.json worker.mjs ./
RUN mkdir -p /jobs \
    && chown renderer:renderer /renderer /jobs \
    && rm -rf \
      /usr/local/lib/node_modules/npm \
      /usr/local/lib/node_modules/corepack \
      /usr/local/bin/npm \
      /usr/local/bin/npx \
      /opt/yarn-v* \
      /usr/local/bin/yarn \
      /usr/local/bin/yarnpkg \
      /usr/local/bin/corepack

USER 10001:10001
ENTRYPOINT ["node", "/renderer/worker.mjs"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 CMD test -s /jobs/.renderer-ready
