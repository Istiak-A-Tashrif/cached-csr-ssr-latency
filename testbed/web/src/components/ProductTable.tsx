"use client";

import { useEffect } from "react";

export type Row = {
  id: number;
  name: string;
  category: string;
  total_orders: string;
  avg_rating: string;
  stock: number;
};

type Props = {
  rows: Row[];
  page: number;
  limit: number;
  respId: string;
  navigate: (page: number, limit: number, aid: string) => void;
};

declare global {
  interface Window {
    __nav?: (page: number, limit: number, aid?: string) => void;
    __commits?: { id: string; respId: string; t: number }[];
  }
}

export default function ProductTable({ rows, page, limit, respId, navigate }: Props) {
  const id = `data-p${page}-l${limit}`;

  // Harness entry point: marks the action start, then navigates.
  useEffect(() => {
    window.__nav = (p, l, aid = "") => {
      performance.mark(`nav-p${p}-l${l}`);
      navigate(p, l, aid);
    };
  }, [navigate]);

  // Secondary endpoint: React commit time of this data (after hydration for SSR).
  useEffect(() => {
    (window.__commits ??= []).push({ id, respId, t: performance.now() });
  }, [id, respId]);

  return (
    // key forces a new element per view so Element Timing reports each render.
    <table key={`${id}-${respId}`} data-view={id} data-resp-id={respId}>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.id} data-pid={r.id}>
            {/* Chromium reports text Element Timing for block-level containers, not inline spans. */}
            <td elementtiming={i === 0 ? id : undefined} data-vis={i === 0 ? id : undefined}>
              {r.name}
            </td>
            <td>{r.category}</td>
            <td>{r.total_orders}</td>
            <td>{Number(r.avg_rating).toFixed(2)}</td>
            <td>{r.stock}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
