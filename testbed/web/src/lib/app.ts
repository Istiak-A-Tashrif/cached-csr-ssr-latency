// Which application the shared CSR/SSR pages render (TWEB revision B5). "catalogue" (default) is the
// original product catalogue; "conduit" reads RealWorld article n (slug "a<n>") from the Conduit API
// and shows it as one row (id n, title, author, tags, body length, favourites count in the column the
// staleness oracle reads). Framework code, cache layers and instrumentation are shared by both.
import type { Row } from "@/components/ProductTable";

export type AppName = "catalogue" | "conduit";

export function dataUrl(app: AppName, apiUrl: string, page: number, limit: number, caller: string, rid?: string) {
  const r = rid ? `&rid=${rid}` : "";
  return app === "conduit"
    ? `${apiUrl}/api/articles/a${page}?caller=${caller}${r}`
    : `${apiUrl}/api/products?page=${page}&limit=${limit}&caller=${caller}${r}`;
}

export function toView(app: AppName, page: number, body: any): { respId: string; data: Row[] } {
  if (app !== "conduit") return body;
  const a = body.article;
  return {
    respId: body.respId,
    data: [{ id: page, name: a.title, category: a.author.username, total_orders: a.tagList.join(" "), avg_rating: String(a.body.length), stock: a.favoritesCount }],
  };
}
