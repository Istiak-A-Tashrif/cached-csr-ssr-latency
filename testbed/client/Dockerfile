FROM mcr.microsoft.com/playwright:v1.56.1-noble
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/runner
RUN npm init -y >/dev/null && npm install playwright@1.56.1
ENV NODE_PATH=/opt/runner/node_modules
COPY --from=netem netem.sh /usr/local/bin/netem.sh
COPY --from=netem tcprtt.mjs /usr/local/lib/tcprtt.mjs
WORKDIR /runner
