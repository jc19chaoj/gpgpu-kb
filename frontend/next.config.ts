import type { NextConfig } from "next";

// Where the Next server should forward /api/* on the server side. Defaults to
// the loopback backend on the same host (works for `./start.sh`). Override
// with KB_BACKEND_URL=http://backend:8000 inside docker-compose.
const BACKEND_URL = process.env.KB_BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle so the Docker runtime image only
  // needs `.next/standalone` + `.next/static` + `public/` (no node_modules).
  output: "standalone",
  async redirects() {
    // Old /search?q=... is now folded into the home page.
    // Keep the URL working for any bookmark or external link.
    return [
      {
        source: "/search",
        destination: "/",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    // Proxy /api/* through the Next server so the browser only ever talks to
    // the same origin it loaded the page from. Fixes LAN access where the
    // client's `localhost` is not the deployment host, and sidesteps CORS.
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
