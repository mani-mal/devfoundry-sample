# DevFoundry Worker Service
FROM node:20-alpine

WORKDIR /app

# Use HTTP repos (lab environment does not trust the Alpine CDN TLS chain)
RUN sed -i 's/https/http/g' /etc/apk/repositories

# Install build dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    openssl-dev \
    libpq-dev

# Copy package files
COPY packages/worker/package*.json ./
COPY packages/core/package*.json ./
COPY packages/integrations/routeforge/package*.json ./
COPY packages/integrations/opencode/package*.json ./
COPY packages/integrations/context-forge/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY packages/worker/src ./src
COPY packages/core/src ./src
COPY packages/integrations/routeforge/src ./src
COPY packages/integrations/opencode/src ./src
COPY packages/integrations/context-forge/src ./src

# Build TypeScript
RUN npx tsc --build

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

USER nodejs

EXPOSE 3002

CMD ["node", "dist/index.js"]
