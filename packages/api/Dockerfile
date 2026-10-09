# DevFoundry API Service
FROM node:20-alpine AS builder

WORKDIR /app

COPY packages/api/package*.json ./
RUN npm install --no-audit --no-fund

COPY packages/api/tsconfig.json ./
COPY packages/api/src ./src

RUN npm run build

# Production
FROM node:20-alpine

WORKDIR /app

RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

COPY --from=builder /app/dist ./dist
COPY packages/api/package*.json ./

RUN npm install --omit=dev --no-audit --no-fund && npm cache clean --force

RUN chown -R nodejs:nodejs /app

EXPOSE 3000

USER nodejs

CMD ["node", "dist/index.js"]
