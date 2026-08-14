# Revision Prompt 16, task: Dockerfiles + docker-compose + deployment
# docs. Standard Next.js standalone-output multi-stage build
# (next.config.ts's `output: "standalone"`) — the runtime image ships
# only the production dependency subset Next's own trace determined it
# actually needs, not the full node_modules tree.
#
# `NEXT_PUBLIC_API_URL` is a *build-time* value: Next.js inlines
# `NEXT_PUBLIC_*` vars into the client JS bundle during `next build`, so
# it must be supplied as a build ARG (see infra/docker-compose.yml),
# not a container-runtime env var — changing it means rebuilding the
# image, not just restarting the container.

# node:22 (not 20): the pnpm version pinned in package.json's
# `packageManager` field requires Node >=22.13 to run at all (it uses
# the `node:sqlite` built-in, added in 22.5) -- corepack downloads and
# executes that exact pnpm version regardless of which Node image it's
# running on, so the base image has to satisfy pnpm's own floor, not
# just this app's.
FROM node:22-alpine AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
