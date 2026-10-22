# Conduit (RealWorld) backend for the TWEB revision's second application (B5).
# The application code is the reference Node/Express/Prisma implementation, fetched at a pinned commit
# and used unmodified (routes, services, Prisma schema and queries). bench/ adds only an entry point:
# request logging, a Redis read-through layer, admin endpoints and seeding (see bench/main.ts).
FROM node:20.18.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates openssl iproute2 iputils-ping && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ARG CONDUIT_COMMIT=30b68e1e881462b2f4164ea09ab4c4f5699c7b0b
RUN git clone https://github.com/gothinkster/node-express-realworld-example-app.git . && git checkout ${CONDUIT_COMMIT} && rm -rf .git
RUN npm ci --ignore-scripts && npx prisma generate --schema src/prisma/schema.prisma
RUN npm install --no-save redis@5.10.0
COPY bench ./bench
RUN npx esbuild bench/main.ts --bundle --platform=node --target=node20 --external:@prisma/client --external:redis --outfile=dist/bench.js
COPY --from=netem netem.sh /usr/local/bin/netem.sh
COPY --from=netem tcprtt.mjs /usr/local/lib/tcprtt.mjs
ENV PORT=5001
# The conduit database lives in the shared Postgres container; create it on first start (an error
# from an existing database is ignored), then apply the reference implementation's migrations.
CMD ["sh", "-c", "echo 'CREATE DATABASE conduit' | npx prisma db execute --url postgresql://postgres:postgres@db:5432/postgres --stdin || true; npx prisma migrate deploy --schema src/prisma/schema.prisma && node dist/bench.js"]
