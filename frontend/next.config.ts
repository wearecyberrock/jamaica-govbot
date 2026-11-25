import type { NextConfig } from "next";

const isDesktopExport = process.env.DESKTOP_EXPORT === "1";
const backendUrl = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  images: { unoptimized: true },
  ...(isDesktopExport
    ? {
        output: "export",
        trailingSlash: true,
      }
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `${backendUrl}/api/:path*`,
            },
            {
              source: "/mcp",
              destination: `${backendUrl}/mcp`,
            },
            {
              source: "/health",
              destination: `${backendUrl}/health`,
            },
          ];
        },
      }),
};

export default nextConfig;
