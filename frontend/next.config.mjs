/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    // Proxy all /api/* to the backend server-side so the browser talks to the
    // Next origin only — sidesteps backend CORS entirely. The voice WebSocket
    // connects directly to the API (no CORS preflight) and is unaffected.
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
