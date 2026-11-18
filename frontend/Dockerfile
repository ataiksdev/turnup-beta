FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Reproducible installs from the lockfile (npm install would re-resolve versions).
RUN npm ci --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# Baked in at build time by Next.js:
#  - API_PROXY_ORIGIN: where the server forwards the browser's same-origin /api/* calls
#    (the backend's address inside the docker network).
#  - NEXT_PUBLIC_API_URL: leave empty to use that proxy; set it only if browsers should
#    call a public API URL directly (then configure ALLOWED_ORIGINS on the backend).
ARG API_PROXY_ORIGIN=http://backend:8000
ARG NEXT_PUBLIC_API_URL=
ENV API_PROXY_ORIGIN=$API_PROXY_ORIGIN NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static
COPY --from=builder --chown=app:app /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]
