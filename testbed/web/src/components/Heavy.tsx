"use client";

import { useMemo } from "react";
import { heavyData } from "@/lib/heavy";

// Experiment Q: forces the heavy module into the route's client bundle and does some
// client work with it (a checksum), as a real heavy dependency would at hydration.
export default function Heavy() {
  const sum = useMemo(() => heavyData.reduce((a, s) => (a * 31 + s.charCodeAt(7)) >>> 0, 7), []);
  return <span hidden data-heavy={sum} />;
}
