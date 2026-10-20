import { renderSsr } from "./render";

export default async function SsrPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  return renderSsr({ searchParams });
}
