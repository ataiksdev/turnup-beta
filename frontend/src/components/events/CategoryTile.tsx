import Link from "next/link";
import type { CSSProperties, MouseEventHandler } from "react";
import { Laugh, Leaf, Monitor, Moon, Music, Palette, Trophy, Utensils, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** The browse categories. Each has its own colour; everything else about a tile (background,
 *  text, border, corners, shadow, hover) comes from the active theme, so the tiles follow
 *  every theme in light and dark. */
export const CATEGORIES: { label: string; slug: string; icon: LucideIcon; hue: string }[] = [
  { label: "Music",     slug: "music",     icon: Music,    hue: "#22C55E" },
  { label: "Nightlife", slug: "nightlife", icon: Moon,     hue: "#8B5CF6" },
  { label: "Arts",      slug: "arts",      icon: Palette,  hue: "#EC4899" },
  { label: "Food",      slug: "food",      icon: Utensils, hue: "#F97316" },
  { label: "Tech",      slug: "tech",      icon: Monitor,  hue: "#0EA5E9" },
  { label: "Sports",    slug: "sports",    icon: Trophy,   hue: "#EF4444" },
  { label: "Comedy",    slug: "comedy",    icon: Laugh,    hue: "#EAB308" },
  { label: "Wellness",  slug: "wellness",  icon: Leaf,     hue: "#14B8A6" },
];

/** A category link tile. "sm": compact, icon above the label (4 across). "lg": a taller card
 *  with the label at the top and the icon badge in the corner (2 across). */
export function CategoryTile({ category, size = "lg", onClick }: {
  category: (typeof CATEGORIES)[number];
  size?: "sm" | "lg";
  onClick?: MouseEventHandler<HTMLAnchorElement>;
}) {
  const { label, slug, icon: Icon, hue } = category;
  // Tinted with the category colour over the theme's card colour, so the text stays readable.
  const style = {
    "--cat": hue,
    backgroundColor: "color-mix(in srgb, var(--cat) 18%, rgb(var(--bg-card)))",
    backgroundImage: "radial-gradient(120% 90% at 100% 100%, color-mix(in srgb, var(--cat) 28%, transparent) 0%, transparent 60%)",
  } as CSSProperties;
  const badge = (px: number) => (
    <span aria-hidden className="grid place-items-center rounded-full shadow-brutal-sm border-2 border-border"
      style={{ width: px, height: px, backgroundColor: "var(--cat)", color: "#0B0B12" }}>
      <Icon size={Math.round(px * 0.52)} strokeWidth={2.4} />
    </span>
  );
  return (
    <Link href={`/discover?category=${slug}`} onClick={onClick} style={style}
      className={cn(
        "relative overflow-hidden rounded-md border-2 border-border shadow-brutal-sm transition-all duration-150",
        "hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal",
        size === "sm" ? "flex flex-col items-center justify-center gap-1.5 h-20" : "block h-24",
      )}>
      {size === "sm" ? (
        <>
          {badge(32)}
          <span className="text-[10px] font-black text-text uppercase tracking-wide leading-none">{label}</span>
        </>
      ) : (
        <>
          <span className="absolute top-3 left-3 text-sm font-black text-text uppercase tracking-wide">{label}</span>
          <span className="absolute bottom-2.5 right-2.5">{badge(40)}</span>
        </>
      )}
    </Link>
  );
}
