"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import ProductTable, { Row } from "@/components/ProductTable";

export default function SsrView({ basePath = "/ssr", extra = null, ...props }: { rows: Row[]; page: number; limit: number; respId: string; basePath?: string; extra?: React.ReactNode }) {
  const router = useRouter();
  // SSR navigation: the server renders the new view (RSC request).
  const navigate = useCallback(
    // `a` tags the action for log correlation; it is not part of the API URL,
    // so it does not affect the Next data-cache key.
    (p: number, l: number, aid: string) => router.push(`${basePath}?page=${p}&limit=${l}&a=${aid}`),
    [router, basePath]
  );
  return (
    <>
      <ProductTable {...props} navigate={navigate} />
      {extra}
    </>
  );
}
