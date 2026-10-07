FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY packages/api/package.json packages/api/tsconfig.json ./
COPY package.json package-lock.json ./
RUN npm ci --only=production

# Copy source
COPY packages/api/src ./dist/packages/api/src
COPY packages/core/src ./dist/packages/core/src
COPY packages/integrations/routeforge/src ./dist/packages/integrations/routeforge/src
COPY packages/integrations/opencode/src ./dist/packages/integrations/opencode/src
COPY packages/integrations/context-forge/src ./dist/packages/integrations/context-forge/src

# Build
RUN npm run build

# Expose port
EXPOSE 3000

# Run
CMD ["node", "dist/packages/api/src/index.js"]
