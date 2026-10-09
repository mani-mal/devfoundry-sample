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

# Install dependencies (dev included: TypeScript is needed for the build)
RUN npm install

# Copy source code
COPY packages/worker/src ./src
COPY packages/core/src ./core/src
COPY packages/integrations/routeforge/src ./routeforge/src
COPY packages/integrations/opencode/src ./opencode/src
COPY packages/integrations/context-forge/src ./contextforge/src

# Install dependencies for the source dependencies and build them first
WORKDIR /app/core
RUN npm install --omit=dev && npx tsc --build
WORKDIR /app/routeforge
RUN npm install --omit=dev && npx tsc --build
WORKDIR /app/opencode
RUN npm install --omit=dev && npx tsc --build
WORKDIR /app/contextforge
RUN npm install --omit=dev && npx tsc --build

# Build TypeScript
RUN npx tsc --build

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

USER nodejs

EXPOSE 3002

CMD ["node", "dist/index.js"]
