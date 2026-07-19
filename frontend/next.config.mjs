// The regular web deploy (Docker/docker-compose) needs a real server: dynamic routes like
// /events/[id], /profile/[username], /tickets/[id] etc. are unbounded and render on demand.
// "output: export" (fully static, zero server) only works for the Capacitor mobile bundle,
// which pre-strips /admin and doesn't need those dynamic pages to be independently linkable —
// see scripts/strip-admin.js and the build:capacitor script.
const isCapacitorBuild = process.env.CAPACITOR_BUILD === "true";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: isCapacitorBuild ? "export" : "standalone",
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
