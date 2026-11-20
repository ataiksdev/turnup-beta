import { Suspense } from "react";
import type { Metadata } from "next";
import { EventDetailClient } from "./EventDetailClient";
import { staticParams } from "@/lib/staticParams";

// Server-side fetch (link-preview metadata). API_PROXY_ORIGIN is read at runtime, so it can
// point at the backend's internal address (e.g. http://backend:8000 in docker-compose);
// NEXT_PUBLIC_* values are frozen into the build.
const API = process.env.API_PROXY_ORIGIN ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const revalidate = 0;
export function generateStaticParams() {
  return staticParams("id");
}

export async function generateMetadata(
  { params }: { params: Promise<{ id: string }> },
): Promise<Metadata> {
  // Next 16: params is a Promise (synchronous access was removed, which made the old
  // params.id undefined and broke every event page).
  const { id } = await params;
  try {
    const res = await fetch(`${API}/api/events/${encodeURIComponent(id)}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return { title: "Event · Turnup" };
    const event = await res.json();
    const desc = event.description?.slice(0, 160) ?? "Discover this event on Turnup.";
    const url  = `${SITE}/events/${id}`;
    const images = event.cover_image ? [{ url: event.cover_image, width: 1200, height: 630 }] : [];

    return {
      title: event.title,
      description: desc,
      alternates: { canonical: url },
      openGraph: {
        title: event.title,
        description: desc,
        url,
        type: "website",
        siteName: "Turnup",
        images,
      },
      twitter: {
        card: "summary_large_image",
        title: event.title,
        description: desc,
        images: event.cover_image ? [event.cover_image] : [],
      },
    };
  } catch {
    return { title: "Event · Turnup" };
  }
}

export default function EventPage() {
  return <Suspense><EventDetailClient /></Suspense>;
}
