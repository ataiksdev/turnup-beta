import type { Metadata } from "next";
import { CommunityDetailClient } from "./CommunityDetailClient";

const API  = process.env.NEXT_PUBLIC_API_URL  ?? "http://localhost:8000";
const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "";

export const revalidate = 0;
export function generateStaticParams() {
  return [];
}

export async function generateMetadata(
  { params }: { params: { slug: string } },
): Promise<Metadata> {
  try {
    const res = await fetch(`${API}/api/communities/${params.slug}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return { title: "Community · Turnup" };
    const c = await res.json();
    const desc = c.description?.slice(0, 160)
      ?? `Join ${c.name} on Turnup — ${c.member_count} members.`;
    const url = `${SITE}/communities/${params.slug}`;
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
  return <CommunityDetailClient />;
}
