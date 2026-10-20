import { renderSsr } from "../ssr/render";
import Heavy from "@/components/Heavy";

// Experiment Q: the SSR page with a heavy client bundle (same data path and caches).
export default async function SsrHeavyPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  return renderSsr({ searchParams, basePath: "/ssrh", extra: <Heavy /> });
}
