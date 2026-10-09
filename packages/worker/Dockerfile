# DevFoundry Worker Service
FROM node:20-alpine AS builder

WORKDIR /app

# Use HTTP repos (lab environment does not trust the Alpine CDN TLS chain)
RUN sed -i 's/https/http/g' /etc/apk/repositories

RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    openssl-dev \
    libpq-dev

# Copy manifests first for layer caching
COPY package.json package-lock.json ./
COPY packages/core/package.json packages/core/
COPY packages/worker/package.json packages/worker/tsconfig.json ./
COPY packages/integrations/routeforge/package.json packages/integrations/routeforge/
COPY packages/integrations/opencode/package.json packages/integrations/opencode/
COPY packages/integrations/context-forge/package.json packages/integrations/context-forge/

# Install workspace dependencies (dev included: TypeScript is needed to build)
RUN npm ci

# Copy source
COPY packages/core/src packages/core/src
COPY packages/worker/src packages/worker/src
COPY packages/worker/tsconfig.json packages/worker/tsconfig.json
COPY packages/integrations/routeforge/src packages/integrations/routeforge/src
COPY packages/integrations/opencode/src packages/integrations/opencode/src
COPY packages/integrations/context-forge/src packages/integrations/context-forge/src

# Build bottom-up
RUN npx tsc --build packages/core && \
    npx tsc --build packages/integrations/routeforge && \
    npx tsc --build packages/integrations/opencode && \
    npx tsc --build packages/integrations/context-forge && \
    npx tsc --build packages/worker

FROM node:20-alpine

WORKDIR /app

RUN apk add --no-cache openssl-dev libpq-dev && \
    addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

COPY --from=builder /app/packages/worker/dist ./dist
COPY --from=builder /app/packages/core/dist ./dist
COPY --from=builder /app/packages/integrations/routeforge/dist ./dist
COPY --from=builder /app/packages/integrations/opencode/dist ./dist
COPY --from=builder /app/packages/integrations/context-forge/dist ./dist
COPY --from=builder /app/node_modules ./node_modules

USER nodejs

EXPOSE 3002

CMD ["node", "dist/index.js"]
