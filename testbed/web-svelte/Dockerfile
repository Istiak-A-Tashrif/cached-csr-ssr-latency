FROM node:22.11.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build
COPY --from=netem netem.sh /usr/local/bin/netem.sh
COPY --from=netem tcprtt.mjs /usr/local/lib/tcprtt.mjs
ENV HOST=0.0.0.0 PORT=3000
CMD ["node", "build"]
