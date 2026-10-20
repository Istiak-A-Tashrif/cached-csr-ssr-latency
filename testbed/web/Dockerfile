FROM node:22.11.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
COPY --from=netem netem.sh /usr/local/bin/netem.sh
COPY --from=netem tcprtt.mjs /usr/local/lib/tcprtt.mjs
# Fresh container = cold Next data cache; also drop any on-disk fetch cache.
CMD ["sh", "-c", "rm -rf .next/cache/fetch-cache && npm start"]
