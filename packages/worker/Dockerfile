FROM node:20-alpine AS builder

WORKDIR /app

# Install root dependencies
COPY package.json package-lock.json ./
RUN npm install
RUN npm install --save-dev --save-exact typescript @types/node @types/jest @types/express @types/uuid @types/pg

# Install core dependencies
COPY packages/core/package.json packages/core/tsconfig.json ./packages/core/
WORKDIR /app/packages/core
RUN npm install
RUN npm install --save-dev --save-exact typescript @types/node @types/jest @types/pg @types/uuid

# Install worker dependencies  
WORKDIR /app
COPY packages/worker/package.json packages/worker/tsconfig.json ./packages/worker/
WORKDIR /app/packages/worker
RUN npm install
RUN npm install --save-dev --save-exact typescript @types/node @types/jest @types/express @types/uuid @types/pg

# Install integrations dependencies
RUN mkdir -p /app/packages/integrations/routeforge /app/packages/integrations/opencode /app/packages/integrations/context-forge
COPY packages/integrations/routeforge/package.json /app/packages/integrations/routeforge/package.json
COPY packages/integrations/routeforge/tsconfig.json /app/packages/integrations/routeforge/tsconfig.json
WORKDIR /app/packages/integrations/routeforge
RUN npm install

COPY packages/integrations/opencode/package.json /app/packages/integrations/opencode/package.json
COPY packages/integrations/opencode/tsconfig.json /app/packages/integrations/opencode/tsconfig.json
WORKDIR /app/packages/integrations/opencode
RUN npm install

COPY packages/integrations/context-forge/package.json /app/packages/integrations/context-forge/package.json
COPY packages/integrations/context-forge/tsconfig.json /app/packages/integrations/context-forge/tsconfig.json
WORKDIR /app/packages/integrations/context-forge
RUN npm install

# Copy all source files
WORKDIR /app
COPY packages/worker/src ./packages/worker/src
COPY packages/core/src ./packages/core/src
COPY packages/integrations/routeforge/src ./packages/integrations/routeforge/src
COPY packages/integrations/opencode/src ./packages/integrations/opencode/src
COPY packages/integrations/context-forge/src ./packages/integrations/context-forge/src

# Build core first
WORKDIR /app/packages/core
RUN /app/node_modules/.bin/tsc --build

# Build integrations
WORKDIR /app/packages/integrations/routeforge
RUN /app/node_modules/.bin/tsc --build

WORKDIR /app/packages/integrations/opencode
RUN /app/node_modules/.bin/tsc --build

WORKDIR /app/packages/integrations/context-forge
RUN /app/node_modules/.bin/tsc --build

# Build worker
WORKDIR /app/packages/worker
RUN /app/node_modules/.bin/tsc --build

FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/packages/worker/dist ./dist/packages/worker
COPY --from=builder /app/packages/core/dist ./dist/packages/core
COPY --from=builder /app/packages/integrations/routeforge/dist ./dist/packages/integrations/routeforge
COPY --from=builder /app/packages/integrations/opencode/dist ./dist/packages/opencode
COPY --from=builder /app/packages/integrations/context-forge/dist ./dist/packages/integrations/context-forge
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3002

CMD ["node", "dist/packages/worker/src/index.js"]
