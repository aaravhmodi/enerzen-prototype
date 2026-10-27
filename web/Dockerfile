# The web app, built against the API address it will call from the browser.
FROM node:22-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ARG NEXT_PUBLIC_API_URL
# Where the web server forwards /api (the API service on the compose network).
ARG API_PROXY_TARGET=
# A public Mapbox token (pk.…) for the zoning map; the map shows a notice without one.
ARG NEXT_PUBLIC_MAPBOX_TOKEN=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL API_PROXY_TARGET=$API_PROXY_TARGET NEXT_PUBLIC_MAPBOX_TOKEN=$NEXT_PUBLIC_MAPBOX_TOKEN NEXT_TELEMETRY_DISABLED=1
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
