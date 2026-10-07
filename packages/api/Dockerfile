FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies including devDependencies for build
COPY packages/api/package.json packages/api/tsconfig.json ./
COPY package.json package-lock.json ./
RUN npm install
RUN npm install --save-dev --save-exact typescript @types/node @types/jest @types/express @types/uuid

# Copy source
COPY packages/api/src ./packages/api/src
COPY packages/core/src ./packages/core/src
COPY packages/integrations/routeforge/src ./packages/integrations/routeforge/src
COPY packages/integrations/opencode/src ./packages/integrations/opencode/src
COPY packages/integrations/context-forge/src ./packages/integrations/context-forge/src

# Build core first
WORKDIR /app/packages/core
RUN ../node_modules/.bin/tsc --build

# Build integrations
WORKDIR /app/packages/integrations/routeforge
RUN ../../node_modules/.bin/tsc --build

WORKDIR /app/packages/integrations/opencode
RUN ../../node_modules/.bin/tsc --build

WORKDIR /app/packages/integrations/context-forge
RUN ../../node_modules/.bin/tsc --build

# Build api
WORKDIR /app/packages/api
RUN ../../node_modules/.bin/tsc --build

FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/packages/api/dist ./dist/packages/api
COPY --from=builder /app/packages/core/dist ./dist/packages/core
COPY --from=builder /app/packages/integrations/routeforge/dist ./dist/packages/integrations/routeforge
COPY --from=builder /app/packages/integrations/opencode/dist ./dist/packages/opencode
COPY --from=builder /app/packages/integrations/context-forge/dist ./dist/packages/integrations/context-forge
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000

CMD ["node", "dist/packages/api/src/index.js"]
