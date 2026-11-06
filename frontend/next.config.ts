import type { NextConfig } from "next";

// Allt under /api gar vidare till FastAPI. Poangen ar att webblasaren bara
// ser en origin: inloggningscookien blir forstahandscookie och CSRF-kontrollen
// i backend (require_same_origin) far ratt Origin-huvud utan undantag.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Standalone-utdata gor containern liten: Next tar med bara de moduler
  // som faktiskt importeras, i stallet for hela node_modules.
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/health", destination: `${API_URL}/health` },
    ];
  },
};

export default nextConfig;
