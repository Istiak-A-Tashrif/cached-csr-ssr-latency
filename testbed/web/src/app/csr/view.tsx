"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useCallback } from "react";
import ProductTable from "@/components/ProductTable";

declare global {
  interface Window {
    __tq?: { key: string; t: number; rid: string }[];
  }
}

export default function CsrView({ apiUrl, feCache, staleMs = Infinity, basePath = "/csr", extra = null }: { apiUrl: string; feCache: boolean; staleMs?: number; basePath?: string; extra?: React.ReactNode }) {
  const sp = useSearchParams();
  const page = Number(sp.get("page") ?? 1);
  const limit = Number(sp.get("limit") ?? 25);

  const { data } = useQuery({
    queryKey: ["products", page, limit],
    queryFn: async () => {
      // crypto.randomUUID is unavailable on plain-http origins (not a secure context).
      const rid = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      // Every queryFn call is a TanStack miss; rid links it to the API log.
      (window.__tq ??= []).push({ key: `p${page}-l${limit}`, t: performance.now(), rid });
      const res = await fetch(
        `${apiUrl}/api/products?page=${page}&limit=${limit}&caller=client&rid=${rid}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    // off: never serve cached data (gcTime 0 drops it on unmount, so no
    // stale-while-refetching display either).
    // Item 8: finite staleTime in ttl/push modes (a stale revisit SHOWS cached data, then refetches).
    staleTime: feCache ? staleMs : 0,
    gcTime: feCache ? Infinity : 0,
  });

  // CSR navigation: client-only URL change, no server round trip.
  const navigate = useCallback((p: number, l: number, aid: string) => {
    window.history.pushState(null, "", `${basePath}?page=${p}&limit=${l}&a=${aid}`);
  }, [basePath]);

  if (!data) return <p data-loading>Loading…</p>;
  return (
    <>
      <ProductTable rows={data.data} page={page} limit={limit} respId={data.respId} navigate={navigate} />
      {extra}
    </>
  );
}
