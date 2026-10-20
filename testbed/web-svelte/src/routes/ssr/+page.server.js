import fs from "fs";
import { env } from "$env/dynamic/private";

// SvelteKit has no built-in data cache equivalent to Next.js `force-cache`, so the SSR
// route uses an in-process server cache shared by all users (FE_CACHE=on), the closest
// framework-level analogue. Logged in the same format as the Next.js app (field name kept).
const cache = new Map();
const seen = new Set();

export async function load({ url }) {
	const page = Number(url.searchParams.get("page") ?? 1);
	const limit = Number(url.searchParams.get("limit") ?? 25);
	const feCache = env.FE_CACHE === "on";
	const apiUrl = `${env.INTERNAL_API_URL}/api/products?page=${page}&limit=${limit}&caller=web`;
	const t0 = performance.now();
	let body = feCache ? cache.get(apiUrl) : undefined;
	if (!body) {
		body = await (await fetch(apiUrl)).json();
		if (feCache) cache.set(apiUrl, body);
	}
	const fetchMs = performance.now() - t0;
	const replay = seen.has(body.respId);
	seen.add(body.respId);
	fs.appendFileSync(env.LOG_FILE || "/results/web.jsonl", JSON.stringify({
		ts: Date.now(), aid: url.searchParams.get("a"), key: `p${page}-l${limit}`, respId: body.respId,
		nextCache: feCache ? (replay ? "hit" : "miss") : "off", fetchMs,
	}) + "\n");
	return { rows: body.data, page, limit, respId: body.respId };
}
