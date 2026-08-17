# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM node:26-alpine@sha256:aadf416b2cdce311a8811ba3f0608a61b77dbf997500e2eafe781b51f6a0b019

ENV NODE_ENV=production \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser \
    PUPPETEER_SKIP_DOWNLOAD=true

RUN apk add --no-cache chromium rsvg-convert \
    && addgroup --system --gid 10001 renderer \
    && adduser --system --uid 10001 --ingroup renderer --home /renderer renderer

WORKDIR /renderer
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY check-licenses.mjs mermaid-config.json puppeteer-config.json worker.mjs ./
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
