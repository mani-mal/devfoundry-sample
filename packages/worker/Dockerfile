FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY packages/worker/package.json packages/worker/tsconfig.json ./
COPY package.json package-lock.json ./
RUN npm ci --only=production

# Copy source
COPY packages/worker/src ./dist/packages/worker/src
COPY packages/core/src ./dist/packages/core/src
COPY packages/integrations/routeforge/src ./dist/packages/integrations/routeforge/src
COPY packages/integrations/opencode/src ./dist/packages/integrations/opencode/src
COPY packages/integrations/context-forge/src ./dist/packages/integrations/context-forge/src

# Build
RUN npm run build

# Expose port
EXPOSE 3002

# Run
CMD ["node", "dist/packages/worker/src/index.js"]
