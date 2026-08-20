import type { NextConfig } from "next";

const apiOrigin =
  process.env.JOEL_API_INTERNAL ??
  process.env.NEXT_PUBLIC_API ??
  "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async redirects() {
    return [
      { source: "/chat", destination: "/", permanent: false },
      { source: "/connectors", destination: "/integrations", permanent: false },
      { source: "/profile", destination: "/settings/profile", permanent: false },
      { source: "/memories", destination: "/graph", permanent: false },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin.replace(/\/$/, "")}/api/:path*`,
      },
      {
        source: "/mcp",
        destination: `${apiOrigin.replace(/\/$/, "")}/mcp/`,
      },
      {
        source: "/mcp/",
        destination: `${apiOrigin.replace(/\/$/, "")}/mcp/`,
      },
      {
        source: "/mcp/:path*",
        destination: `${apiOrigin.replace(/\/$/, "")}/mcp/:path*`,
      },
      {
        source: "/.well-known/oauth-authorization-server",
        destination: `${apiOrigin.replace(/\/$/, "")}/.well-known/oauth-authorization-server`,
      },
      {
        source: "/.well-known/oauth-protected-resource",
        destination: `${apiOrigin.replace(/\/$/, "")}/.well-known/oauth-protected-resource`,
      },
      {
        source: "/.well-known/oauth-protected-resource/:path*",
        destination: `${apiOrigin.replace(/\/$/, "")}/.well-known/oauth-protected-resource/:path*`,
      },
      {
        source: "/authorize",
        destination: `${apiOrigin.replace(/\/$/, "")}/authorize`,
      },
      {
        source: "/token",
        destination: `${apiOrigin.replace(/\/$/, "")}/token`,
      },
      {
        source: "/register",
        destination: `${apiOrigin.replace(/\/$/, "")}/register`,
      },
      {
        source: "/revoke",
        destination: `${apiOrigin.replace(/\/$/, "")}/revoke`,
      },
    ];
  },
};

export default nextConfig;
