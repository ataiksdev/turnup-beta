import { MapPin, Navigation } from "lucide-react";

/** Venue map + directions. Uses an OpenStreetMap embed (no API key needed) when the event has
 *  coordinates; every physical event gets a "Get directions" link built from its address. */
export function EventMap({ venue, address, city, latitude, longitude }: {
  venue: string; address?: string | null; city?: string | null;
  latitude?: number | null; longitude?: number | null;
}) {
  const hasCoords = typeof latitude === "number" && typeof longitude === "number"
    && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
  const query = hasCoords ? `${latitude},${longitude}` : [venue, address, city].filter(Boolean).join(", ");
  if (!query) return null;
  const directions = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;

  let embed: string | null = null;
  if (hasCoords) {
    const d = 0.006; // ~600 m around the venue
    const bbox = [longitude! - d, latitude! - d, longitude! + d, latitude! + d].map((n) => n.toFixed(5)).join(",");
    embed = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${latitude},${longitude}`;
  }

  return (
    <section aria-label={`Location of ${venue}`} className="rounded border-2 border-border overflow-hidden bg-bg-card">
      {embed && (
        <iframe
          title={`Map showing ${venue}`}
          src={embed}
          className="w-full h-44 border-0 block"
          loading="lazy"
          referrerPolicy="no-referrer"
          sandbox="allow-scripts allow-same-origin"
        />
      )}
      <div className="flex items-center justify-between gap-3 p-3">
        <div className="min-w-0 flex items-start gap-2">
          <MapPin size={16} className="text-primary mt-0.5 shrink-0" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-bold text-text truncate">{venue}</p>
            <p className="text-xs text-text-muted truncate">{[address, city].filter(Boolean).join(", ")}</p>
          </div>
        </div>
        <a href={directions} target="_blank" rel="noopener noreferrer"
          className="shrink-0 inline-flex items-center gap-1 text-xs font-bold text-primary hover:underline">
          <Navigation size={12} aria-hidden /> Get directions
        </a>
      </div>
    </section>
  );
}
