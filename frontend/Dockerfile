# ---------- étape 1 : build Vite ----------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Build + identifiant unique injecté dans le service worker (invalide les anciens caches).
RUN npm run build \
 && sed -i "s/__BUILD_ID__/$(date -u +%Y%m%d%H%M%S)/" dist/sw.js

# ---------- étape 2 : nginx ----------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -qO- http://127.0.0.1/ > /dev/null || exit 1
