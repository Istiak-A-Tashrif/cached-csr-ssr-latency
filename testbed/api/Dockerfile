FROM node:22.11.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY server.js ./
COPY --from=netem netem.sh /usr/local/bin/netem.sh
COPY --from=netem tcprtt.mjs /usr/local/lib/tcprtt.mjs
CMD ["node", "server.js"]
