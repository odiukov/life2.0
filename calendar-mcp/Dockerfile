# life-agents wrapper around nspady/google-calendar-mcp v2.6.1.
# Clones the upstream tag, builds normally, then applies patches.js so the
# server is usable from our orchestrator (stateful sessions + JSON responses).

# syntax=docker/dockerfile:1

FROM node:18-alpine AS builder

RUN apk add --no-cache git

WORKDIR /app
RUN git clone --depth 1 --branch v2.6.1 https://github.com/nspady/google-calendar-mcp.git .

RUN npm ci --no-audit --no-fund --silent
RUN npm run build

COPY patches.js /tmp/patches.js
RUN node /tmp/patches.js

RUN npm prune --production --silent

FROM node:18-alpine

RUN addgroup -g 1001 -S nodejs && \
    adduser -S -u 1001 -G nodejs nodejs

WORKDIR /app
COPY --from=builder --chown=nodejs:nodejs /app /app

RUN mkdir -p /home/nodejs/.config/google-calendar-mcp && \
    chown -R nodejs:nodejs /home/nodejs/.config

USER nodejs
EXPOSE 3000

CMD ["node", "build/index.js"]
