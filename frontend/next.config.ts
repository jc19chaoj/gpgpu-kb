import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
};

export default nextConfig;
