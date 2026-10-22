import fs from "fs";
import SsrView from "./view";
import { AppName, dataUrl, toView } from "@/lib/app";

// Replay detection for the Next data cache: a response id that was already
// returned once by the API can only come back from the data cache.
const g = globalThis as unknown as { __seen?: Set<string> };
const seen = (g.__seen ??= new Set<string>());

// Shared by /ssr and /ssrh (experiment Q); not a page component itself.
export async function renderSsr({
  searchParams,
  basePath,
  extra,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
  basePath?: string;
  extra?: React.ReactNode;
}) {
  const sp = await searchParams;
  const page = Number(sp.page ?? 1);
  const limit = Number(sp.limit ?? 25);
  // FE_CACHE: "off" | "on" (force-cache) | item 8: "ttl" (revalidate R s, tagged) | "push" (force-cache, tagged; revalidated on write)
  const mode = process.env.FE_CACHE || "off";
  const feCache = mode !== "off";
  const tag = `p${page}-l${limit}`;

  const app = (process.env.APP as AppName) || "catalogue";
  const url = dataUrl(app, process.env.INTERNAL_API_URL!, page, limit, "web");
  const t0 = performance.now();
  const opts: RequestInit =
    mode === "ttl" ? { next: { revalidate: Number(process.env.NEXT_REVALIDATE || 2), tags: [tag] } }
    : mode === "push" ? { cache: "force-cache", next: { tags: [tag] } }
    : feCache ? { cache: "force-cache" } : { cache: "no-store" };
  const res = await fetch(url, opts);
  const body = toView(app, page, await res.json());
  const fetchMs = performance.now() - t0;

  const replay = seen.has(body.respId);
  seen.add(body.respId);
  fs.appendFileSync(
    process.env.LOG_FILE || "/results/web.jsonl",
    JSON.stringify({
      ts: Date.now(), aid: sp.a ?? null, key: `p${page}-l${limit}`, respId: body.respId,
      nextCache: feCache ? (replay ? "hit" : "miss") : "off", fetchMs,
    }) + "\n"
  );

  return <SsrView rows={body.data} page={page} limit={limit} respId={body.respId} basePath={basePath} extra={extra} />;
}
