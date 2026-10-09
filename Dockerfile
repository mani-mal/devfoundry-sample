# Multi-stage Docker build for DevFoundry
# Stage 1: Build all packages
FROM node:20-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache python3 make g++ openssl-dev libpq-dev

# Copy package.json files first for caching
COPY package*.json ./
COPY packages/core/package*.json packages/core/
COPY packages/api/package*.json packages/api/
COPY packages/worker/package*.json packages/worker/
COPY packages/cli/package*.json packages/cli/
COPY packages/integrations/routeforge/package*.json packages/integrations/routeforge/
COPY packages/integrations/opencode/package*.json packages/integrations/opencode/
COPY packages/integrations/context-forge/package*.json packages/integrations/context-forge/
COPY packages/web-console/package*.json packages/web-console/

# Install all dependencies
RUN npm ci

# Copy source code
COPY packages/core/src packages/core/src
COPY packages/api/src packages/api/src
COPY packages/worker/src packages/worker/src
COPY packages/cli/src packages/cli/src
COPY packages/integrations/routeforge/src packages/integrations/routeforge/src
COPY packages/integrations/opencode/src packages/integrations/opencode/src
COPY packages/integrations/context-forge/src packages/integrations/context-forge/src
COPY packages/web-console/src packages/web-console/src

# Build all packages
RUN npx tsc --build

# Stage 2: Production images

# DevFoundry API (port 3000)
FROM node:20-alpine AS api

WORKDIR /app

RUN apk add --no-cache openssl-dev libpq-dev && \
    addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

COPY --from=builder /app/packages/api/dist ./dist
COPY --from=builder /app/packages/core/dist ./dist
COPY --from=builder /app/packages/integrations/*/dist ./dist/integrations/

USER nodejs

EXPOSE 3000

CMD ["node", "dist/index.js"]

# DevFoundry Worker (port 3002)
FROM node:20-alpine AS worker

WORKDIR /app

RUN apk add --no-cache openssl-dev libpq-dev && \
    addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

COPY --from=builder /app/packages/worker/dist ./dist
COPY --from=builder /app/packages/core/dist ./dist
COPY --from=builder /app/packages/integrations/*/dist ./dist/integrations/

USER nodejs

EXPOSE 3002

CMD ["node", "dist/index.js"]

# DevFoundry Web Console (port 3001)
FROM node:20-alpine AS web-console

WORKDIR /app

RUN apk add --no-cache openssl-dev && \
    addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

COPY --from=builder /app/packages/web-console/dist ./dist
COPY --from=builder /app/packages/web-console/public ./public

USER nodejs

EXPOSE 3001

CMD ["node", "dist/server.js"]
