"use client";
import { useEffect, useState, type CSSProperties } from "react";
import { Check, Monitor, Moon, Palette, Sun } from "lucide-react";
import { resolveMode, THEME_IDS, THEMES, type ModePreference, type ThemeId, type ThemeMode } from "@/lib/themes";
import { useThemeChoice } from "@/lib/useThemeChoice";
import { cn } from "@/lib/utils";

const MODES: { id: ModePreference; label: string; icon: typeof Sun }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

/** A miniature screen drawn in the theme's own tokens (inline, so it doesn't depend on
 *  the theme currently applied to the page). */
function ThemePreview({ id, mode }: { id: ThemeId; mode: ThemeMode }) {
  const v = THEMES[id].modes[mode] as Record<string, string>;
  const c = (name: string, alpha = 1) => `rgb(${v[name]} / ${alpha})`;
  const style = THEMES[id].style;
  const panelAlpha = Number(v["--surface-alpha"] ?? 1);
  const panel: CSSProperties = {
    background: c("--bg-card", panelAlpha),
    border: `${style === "brutal" ? 2 : 1.5}px solid ${c("--border", Number(v["--border-alpha"] ?? 1))}`,
    borderRadius: v["--radius"],
    boxShadow: v["--shadow-sm"].replaceAll("var(--shadow-color)", v["--shadow-color"]).replaceAll("var(--primary)", v["--primary"]),
    backdropFilter: style === "glass" ? "blur(8px)" : undefined,
  };
  return (
    <div aria-hidden className="h-24 w-full overflow-hidden p-2.5 flex flex-col gap-1.5"
      style={{ backgroundColor: c("--bg"), backgroundImage: v["--page-bg"] === "none" ? undefined : v["--page-bg"],
               borderRadius: `calc(${v["--radius"]} + 2px)` }}>
      <div className="flex-1 p-2 flex flex-col gap-1.5" style={panel}>
        <div className="h-1.5 w-3/5 rounded-full" style={{ background: c("--text") }} />
        <div className="h-1.5 w-2/5 rounded-full" style={{ background: c("--text-muted") }} />
        <div className="mt-auto flex items-center gap-1.5">
          <span className="text-[9px] font-black px-2 py-0.5"
            style={{ background: c("--primary"), color: c("--on-primary"),
                     borderRadius: style === "fluffy" ? "9999px" : v["--radius-sm"] }}>
            Go
          </span>
          <span className="h-1.5 w-8 rounded-full" style={{ background: c("--primary", 0.5) }} />
        </div>
      </div>
    </div>
  );
}

/** Settings -> Appearance: light/dark/system plus the full theme (palette + style). */
export function AppearanceSettings() {
  const { palette, mode, choose } = useThemeChoice();
  // "system" depends on the device, which the server can't know: resolve after mount.
  const [previewMode, setPreviewMode] = useState<ThemeMode>("dark");
  useEffect(() => {
    setPreviewMode(resolveMode(mode));
    if (mode !== "system" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setPreviewMode(resolveMode("system"));
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [mode]);

  return (
    <section className="border-2 border-border rounded bg-bg-card p-4 space-y-4" aria-labelledby="appearance-heading">
      <h2 id="appearance-heading" className="flex items-center gap-2 text-sm font-black uppercase tracking-wide text-text">
        <Palette size={16} /> Appearance
      </h2>

      <div role="radiogroup" aria-label="Light or dark" className="grid grid-cols-3 gap-1 p-1 rounded border-2 border-border bg-bg-elevated">
        {MODES.map(({ id, label, icon: Icon }) => {
          const on = mode === id;
          return (
            <button key={id} type="button" role="radio" aria-checked={on} onClick={() => choose({ mode: id })}
              className={cn("flex items-center justify-center gap-1.5 py-2 rounded text-xs font-bold transition-colors",
                on ? "bg-primary text-on-primary" : "text-text-muted hover:text-text")}>
              <Icon size={14} aria-hidden /> {label}
            </button>
          );
        })}
      </div>
      {mode === "system" && (
        <p className="text-xs text-text-muted -mt-2">Follows your phone or computer: currently {previewMode}.</p>
      )}

      <div role="radiogroup" aria-label="Theme" className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {THEME_IDS.map((id) => {
          const t = THEMES[id];
          const on = palette === id;
          return (
            <button key={id} type="button" role="radio" aria-checked={on} onClick={() => choose({ palette: id })}
              className={cn("text-left rounded border-2 p-1.5 transition-all bg-bg-surface",
                on ? "border-primary shadow-brutal-primary" : "border-border-subtle hover:border-border")}>
              <ThemePreview id={id} mode={previewMode} />
              <span className="flex items-center justify-between gap-1 mt-1.5 px-0.5">
                <span className="text-xs font-black text-text truncate">{t.name}</span>
                {on && <Check size={14} className="text-primary shrink-0" aria-hidden />}
              </span>
              <span className="block px-0.5 text-[10px] leading-tight text-text-muted">{t.blurb}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
