import { revalidateTag } from "next/cache";

// Item 8 push invalidation: the API calls this after each write to expire the page's tag
// immediately (expire: 0), so the next request reads fresh data.
export async function GET(req: Request) {
  const tag = new URL(req.url).searchParams.get("tag");
  if (!tag) return Response.json({ ok: false }, { status: 400 });
  revalidateTag(tag, { expire: 0 });
  return Response.json({ ok: true, tag, at: Date.now() });
}

export const dynamic = "force-dynamic";
