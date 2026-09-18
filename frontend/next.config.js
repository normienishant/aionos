/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy API requests to the FastAPI backend.
  // BACKEND_URL is set in production (e.g. Render); defaults to localhost for dev.
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
