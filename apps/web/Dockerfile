# Pro Clipper web app. Build from the repository root:
#   docker build -f apps/web/Dockerfile .
FROM node:22-slim

WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
RUN npm ci

COPY apps/web apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace apps/web

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npm", "run", "start", "--workspace", "apps/web", "--", "-H", "0.0.0.0", "-p", "3000"]
