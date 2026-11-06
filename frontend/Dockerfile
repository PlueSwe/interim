# Frontend: Next.js i standalone-lage.
#
# Tre steg. Standalone-utdata tar med bara de moduler som faktiskt anvands, sa
# den fardiga avbilden innehaller inget node_modules pa hundratals megabyte och
# ingen byggkedja.
#
# API_URL satts i byggsteget OCH i korsteget. next.config.ts laser den i
# rewrites(), som utvarderas vid korning, men en byggtidsvariabel gor att ett
# felstavat varde syns direkt i stallet for som 502 i drift.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
# npm ci kraver en lockfil. Finns ingen anvands npm install, men da ar bygget
# inte reproducerbart och det ska sagas rakt ut.
RUN if [ -f package-lock.json ]; then npm ci; else \
      echo "VARNING: package-lock.json saknas, bygget ar inte reproducerbart" >&2; \
      npm install; \
    fi


FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG API_URL=http://api:8000
ENV API_URL=$API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build


FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 10002 -S radar && adduser -u 10002 -S radar -G radar

COPY --from=builder --chown=radar:radar /app/.next/standalone ./
COPY --from=builder --chown=radar:radar /app/.next/static ./.next/static
COPY --from=builder --chown=radar:radar /app/public ./public

USER radar
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1

CMD ["node", "server.js"]
