import { Suspense } from "react";
import CsrView from "../csr/view";
import Heavy from "@/components/Heavy";

// Static shell: no data on the server. Config is read at request time and
// passed down so the client bundle does not need a rebuild per configuration.
// Experiment Q: the CSR page with a heavy client bundle.
export default async function CsrHeavyPage() {
  return (
    <Suspense>
      <CsrView
        apiUrl={process.env.PUBLIC_API_URL!}
        feCache={(process.env.FE_CACHE || "off") !== "off"}
        staleMs={process.env.FE_CACHE === "ttl" || process.env.FE_CACHE === "push" ? Number(process.env.TANSTACK_S || 2) * 1000 : Infinity}
        basePath="/csrh"
        extra={<Heavy />}
      />
    </Suspense>
  );
}

export const dynamic = "force-dynamic";
