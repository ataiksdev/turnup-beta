import { Suspense } from "react";
import type { Metadata } from "next";
import { CommunityDetailClient } from "./CommunityDetailClient";
import { staticParams } from "@/lib/staticParams";

// Server-side fetch (link-preview metadata). API_PROXY_ORIGIN is read at runtime, so it can
// point at the backend's internal address (e.g. http://backend:8000 in docker-compose);
// NEXT_PUBLIC_* values are frozen into the build.
const API = process.env.API_PROXY_ORIGIN ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("slug");
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params; // a Promise in Next 16
  try {
    const res = await fetch(`${API}/api/communities/${encodeURIComponent(slug)}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return { title: "Community · Turnup" };
    const c = await res.json();
    const desc = c.description?.slice(0, 160)
      ?? `Join ${c.name} on Turnup — ${c.member_count} members.`;
    const url = `${SITE}/communities/${slug}`;
    const images = c.cover_image
      ? [{ url: c.cover_image, width: 1200, height: 630 }]
      : [];

    return {
      title: c.name,
      description: desc,
      alternates: { canonical: url },
      openGraph: {
        title: c.name,
        description: desc,
        url,
        type: "website",
        siteName: "Turnup",
        images,
      },
      twitter: {
        card: "summary_large_image",
        title: c.name,
        description: desc,
        images: c.cover_image ? [c.cover_image] : [],
      },
    };
  } catch {
    return { title: "Community · Turnup" };
  }
}

export default function CommunityPage() {
  return <Suspense><CommunityDetailClient /></Suspense>;
}
