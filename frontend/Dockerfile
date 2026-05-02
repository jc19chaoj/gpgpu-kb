# syntax=docker/dockerfile:1.7
# Frontend image: Next.js 16 standalone output (App Router + React 19)

# ---------- deps ----------
FROM node:20-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat

# Allow swapping the npm registry at build time. Useful when registry.npmjs.org
# is unreachable / rate-limited (e.g. in some regions). Examples:
#   --build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry "$NPM_REGISTRY"

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund --prefer-offline=false --fetch-retries=5 --fetch-retry-mintimeout=20000

# ---------- builder ----------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* is baked at build time into the client bundle. Default is
# empty so the browser uses relative /api/* URLs and the Next server proxies
# them to the backend. Only set this if you want browsers to bypass the proxy
# and hit the backend directly (then CORS must allow that origin).
#   --build-arg NEXT_PUBLIC_API_URL=https://kb.example.com
ARG NEXT_PUBLIC_API_URL=

# Server-side rewrite destination for /api/*. Next.js bakes this into
# routes-manifest.json during `next build`, so it MUST be set at build time
# (runtime env is ignored). Default targets the docker-compose `backend`
# service. For bare-metal/host networking, override with:
#   --build-arg KB_BACKEND_URL=http://127.0.0.1:8000
ARG KB_BACKEND_URL=http://backend:8000

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    KB_BACKEND_URL=$KB_BACKEND_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ---------- runner ----------
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Run as non-root.
RUN addgroup --system --gid 1001 nodejs \
    && adduser  --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]
