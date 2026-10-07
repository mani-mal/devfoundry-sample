FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY packages/worker/package.json packages/worker/tsconfig.json ./
COPY package.json package-lock.json ./
RUN npm ci

# Copy source
COPY packages/worker/src ./packages/worker/src
COPY packages/core/src ./packages/core/src
COPY packages/integrations/routeforge/src ./packages/integrations/routeforge/src
COPY packages/integrations/opencode/src ./packages/integrations/opencode/src
COPY packages/integrations/context-forge/src ./packages/integrations/context-forge/src

# Build typescript directly
RUN npx tsc --build packages/worker/tsconfig.json

FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/packages/worker/dist ./dist/packages/worker
COPY --from=builder /app/packages/core/dist ./dist/packages/core
COPY --from=builder /app/packages/integrations/routeforge/dist ./dist/packages/integrations/routeforge
COPY --from=builder /app/packages/integrations/opencode/dist ./dist/packages/integrations/opencode
COPY --from=builder /app/packages/integrations/context-forge/dist ./dist/packages/integrations/context-forge
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3002

CMD ["node", "dist/packages/worker/src/index.js"]
