# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM node:24.22.1-alpine@sha256:6a1c190e17215d844926b0677f4bf87273ff7d5e54db06d3b5b5863ab0b09a3d AS assets
ADD --checksum=sha256:634a578430c7b3c94d33e34f9bec8d1ca91d0fd20201e31b03cbb27803fb0443 https://codeload.github.com/axllent/mailpit/tar.gz/a028b01f4a24b4b36bdad95b8e09e070ebf2bad4 /source.tar.gz
RUN mkdir /src && tar -xzf /source.tar.gz -C /src --strip-components=1
WORKDIR /src
RUN npm ci --no-audit --no-fund && npm run package && rm -rf node_modules /source.tar.gz

FROM golang:1.27.3-alpine@sha256:f2c872bcee949b7be9c490efd02b48a8a2fbf947cdf533f1c58525ec9d8170fd AS builder
ENV GOTOOLCHAIN=local CGO_ENABLED=0
WORKDIR /src
COPY --from=assets /src/ ./
RUN go mod download && go mod verify \
    && go install github.com/google/go-licenses/v2@v2.0.1 \
    && go-licenses report ./... --template .github/third-party-licenses.tpl --ignore github.com/axllent/mailpit > internal/licenses/third-party.txt \
    && go build -trimpath -ldflags "-s -w -X github.com/axllent/mailpit/config.Version=v1.31.6-tekdocs-go1.27.3" -o /mailpit . \
    && go version -m /mailpit

# Match upstream runtime layout without carrying its vulnerable executable layer.
FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
RUN apk upgrade --no-cache && apk add --no-cache tzdata
COPY --from=builder /mailpit /mailpit
RUN ln -sf /mailpit /usr/sbin/sendmail && ln -sf /mailpit /usr/local/bin/sendmail
LABEL org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.upstream.source="https://github.com/axllent/mailpit" \
    org.opencontainers.image.upstream.revision="a028b01f4a24b4b36bdad95b8e09e070ebf2bad4"
EXPOSE 1025 1110 8025
HEALTHCHECK --interval=15s --start-period=10s --start-interval=1s CMD ["/mailpit", "readyz"]
ENTRYPOINT ["/mailpit"]
