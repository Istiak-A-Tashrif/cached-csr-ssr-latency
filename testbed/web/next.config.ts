import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Router Cache for dynamic pages: 0 s so SSR navigation always reaches the
  // server and only the Next data cache can short-circuit the API call.
  experimental: { staleTimes: { dynamic: 0 } },
};

export default nextConfig;
