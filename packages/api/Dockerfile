FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies including devDependencies for build
COPY packages/api/package.json packages/api/tsconfig.json ./
COPY package.json package-lock.json ./
RUN npm --version
RUN npm ci --include=dev
RUN ls node_modules/@types/ | head -10

# Copy source
COPY packages/api/src ./src
COPY packages/core/src ./packages/core/src
COPY packages/integrations/routeforge/src ./packages/integrations/routeforge/src
COPY packages/integrations/opencode/src ./packages/integrations/opencode/src
COPY packages/integrations/context-forge/src ./packages/integrations/context-forge/src

# Build typescript directly
RUN ./node_modules/.bin/tsc --build

FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000

CMD ["node", "dist/src/index.js"]
