import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker
  output: "standalone",
  reactStrictMode: false,
  onDemandEntries: {
    maxInactiveAge: 60 * 60 * 1000, // 1 hour
    pagesBufferLength: 10,
  },
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    const backend =
      process.env.INSPECTRA_DEV_PROXY_URL?.replace(/\/$/, "") ||
      "http://127.0.0.1:8080";
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
  ...(process.env.NODE_ENV === "development" && {
    allowedDevOrigins: [
      "localhost",
      "0.0.0.0",
    ],
  }),
};

export default nextConfig;
