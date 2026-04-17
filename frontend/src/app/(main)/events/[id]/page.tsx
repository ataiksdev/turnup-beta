import type { Metadata } from "next";
import { EventDetailClient } from "./EventDetailClient";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export async function generateMetadata(
  { params }: { params: { id: string } },
): Promise<Metadata> {
  try {
    const res = await fetch(`${API}/api/events/${params.id}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return { title: "Event · Turnup" };
    const event = await res.json();
    const desc = event.description?.slice(0, 160) ?? "Discover this event on Turnup.";
    const url  = `${SITE}/events/${params.id}`;
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

export default function EventPage({ params }: { params: { id: string } }) {
  return <EventDetailClient id={params.id} />;
}
