import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker
  output: "standalone",
  reactStrictMode: false,
  onDemandEntries: {
    maxInactiveAge: 60 * 60 * 1000, // 1 hour
    pagesBufferLength: 10,
  },
  ...(process.env.NODE_ENV === "development" && {
    allowedDevOrigins: ["*"],
  }),
};

export default nextConfig;
