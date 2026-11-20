import { Suspense } from "react";
import type { Metadata } from "next";
import { VenueDetailClient } from "./VenueDetailClient";
import { staticParams } from "@/lib/staticParams";

const API = process.env.API_PROXY_ORIGIN ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("slug");
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  try {
    const res = await fetch(`${API}/api/venues/${encodeURIComponent(slug)}`, { next: { revalidate: 300 } });
    if (!res.ok) return { title: "Venue · Turnup" };
    const v = await res.json();
    const desc = v.description?.slice(0, 160) ?? `Book ${v.name} on Turnup.`;
    return {
      title: `${v.name} · Turnup venues`, description: desc,
      alternates: { canonical: `${SITE}/venues/${slug}` },
      openGraph: { title: v.name, description: desc, url: `${SITE}/venues/${slug}`, siteName: "Turnup",
        images: v.cover_image ? [{ url: v.cover_image }] : [] },
    };
  } catch {
    return { title: "Venue · Turnup" };
  }
}

export default function VenuePage() {
  return <Suspense><VenueDetailClient /></Suspense>;
}
