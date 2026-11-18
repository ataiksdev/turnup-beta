// The regular web deploy (Docker/docker-compose) needs a real server: dynamic routes like
// /events/[id], /profile/[username], /tickets/[id] etc. are unbounded and render on demand.
// "output: export" (fully static, zero server) only works for the Capacitor mobile bundle,
// which pre-strips /admin and doesn't need those dynamic pages to be independently linkable —
// see scripts/strip-admin.js and the build:capacitor script.
const isCapacitorBuild = process.env.CAPACITOR_BUILD === "true";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: isCapacitorBuild ? "export" : "standalone",
  // Same-origin API proxy for local/preview dev: when NEXT_PUBLIC_API_URL is unset (the plain
  // `npm run dev` default), the browser calls relative /api/* paths, which this Next.js server
  // forwards to the backend. This avoids needing CORS/ALLOWED_ORIGINS configuration for local
  // dev, and is what makes testing work behind a tunneled preview (the browser never needs to
  // reach the backend's port directly — only this server's own origin, which it's already on).
  // No-op in production builds that set NEXT_PUBLIC_API_URL (e.g. docker-compose), since those
  // requests go straight to that absolute URL and never hit this rewrite.
  async rewrites() {
    if (isCapacitorBuild) return [];
    const apiOrigin = process.env.API_PROXY_ORIGIN || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
    ];
  },
  images: {
    unoptimized: true,
    dangerouslyAllowSVG: true,
    contentDispositionType: "attachment",
    contentSecurityPolicy: "default-src 'self'; script-src 'none'; sandbox;",
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
      { protocol: "https", hostname: "api.dicebear.com" },
      { protocol: "https", hostname: "*.cloudinary.com" },
    ],
  },
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Service-Worker-Allowed", value: "/" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
      {
        source: "/manifest.json",
        headers: [
          { key: "Cache-Control", value: "public, max-age=3600" },
        ],
      },
    ];
  },
};

export default nextConfig;
