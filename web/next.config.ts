import type { NextConfig } from "next";

const apiOrigin =
  process.env.JOEL_API_INTERNAL ??
  process.env.NEXT_PUBLIC_API ??
  "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
