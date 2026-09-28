import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The console is a backend-for-frontend: the browser only ever talks to
  // this Next.js server, which holds the session and calls the API
  // server-side. Nothing here is exposed to the client bundle.
  reactStrictMode: true,
};

export default nextConfig;
