import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker
  output: "standalone",
  // Allow cross-origin requests in development (for Cypress testing)
  // This allows requests from any origin during development
  ...(process.env.NODE_ENV === "development" && {
    allowedDevOrigins: ["*"],
  }),
};

export default nextConfig;
