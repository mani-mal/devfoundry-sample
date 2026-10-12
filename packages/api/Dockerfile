# DevFoundry API Service
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
COPY package.json ./
COPY packages/core/package.json packages/core/
COPY packages/core/tsconfig.json packages/core/
COPY packages/api/package.json packages/api/
COPY packages/api/tsconfig.json packages/api/
COPY packages/integrations/routeforge/package.json packages/integrations/routeforge/
COPY packages/integrations/routeforge/tsconfig.json packages/integrations/routeforge/

# Install workspace dependencies (dev included: TypeScript is needed to build)
RUN npm install --workspaces --include-workspace-root

# Copy source
COPY packages/core/src packages/core/src
COPY packages/api/src packages/api/src
COPY packages/integrations/routeforge/src packages/integrations/routeforge/src

# Build bottom-up
RUN npx tsc --build packages/integrations/routeforge && \
    npx tsc --build packages/core && \
    npx tsc --build packages/api

FROM node:20-alpine

WORKDIR /app

# Use HTTP repos (lab environment does not trust the Alpine CDN TLS chain)
RUN sed -i 's/https/http/g' /etc/apk/repositories

RUN apk add --no-cache openssl-dev libpq-dev && \
    addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# Keep each package's dist in place: api output at /app/dist,
# deps under /app/packages/* so node_modules symlinks resolve
COPY --from=builder /app/packages/api/dist ./dist
COPY --from=builder /app/packages/core/package.json ./packages/core/package.json
COPY --from=builder /app/packages/core/dist ./packages/core/dist
COPY --from=builder /app/packages/integrations/routeforge/package.json ./packages/integrations/routeforge/package.json
COPY --from=builder /app/packages/integrations/routeforge/dist ./packages/integrations/routeforge/dist
COPY --from=builder /app/node_modules ./node_modules

USER nodejs

EXPOSE 3000

CMD ["node", "dist/index.js"]
