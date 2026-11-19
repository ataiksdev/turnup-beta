import json, sys
sys.path.insert(0, ".")
from styles import S, blend
brutal = json.load(open("palettes.json"))
rgb = lambda h: f"{int(h[0:2],16)} {int(h[2:4],16)} {int(h[4:6],16)}"

BRUTAL_STYLE = {
    "--radius-sm": "1px", "--radius": "1px", "--radius-md": "2px", "--radius-lg": "2px",
    "--shadow-sm": "2px 2px 0 rgb(var(--shadow-color))", "--shadow": "3px 3px 0 rgb(var(--shadow-color))",
    "--shadow-lg": "5px 5px 0 rgb(var(--shadow-color))",
    "--shadow-primary": "3px 3px 0 rgb(var(--primary))", "--shadow-primary-lg": "5px 5px 0 rgb(var(--primary))",
    "--surface-alpha": "1", "--elevated-alpha": "1", "--border-alpha": "1", "--blur": "0px", "--page-bg": "none",
}
themes = {}
for pid, p in brutal.items():
    themes[pid] = {"name": p["name"], "blurb": p["blurb"], "style": "brutal", "swatch": p["swatch"],
                   "chrome": p["chrome"],
                   "modes": {m: {**p["modes"][m], **BRUTAL_STYLE} for m in ("dark", "light")}}

def style_vars(sid, mode, v):
    b, s1, s2 = v["page"][:3]
    common = {"--surface-alpha": str(v["card_alpha"]), "--elevated-alpha": str(v["elevated_alpha"]),
              "--border-alpha": str(v["border_alpha"])}
    if sid == "glass":
        sh = "0 0 0" if mode == "dark" else "30 41 99"
        k = (0.18, 0.28, 0.36) if mode == "dark" else (0.06, 0.10, 0.14)
        page = (f"radial-gradient(60rem 40rem at 0% -10%, rgb({rgb(s1)}) 0%, transparent 65%), "
                f"radial-gradient(55rem 45rem at 100% 15%, rgb({rgb(s2)}) 0%, transparent 60%), "
                f"radial-gradient(45rem 35rem at 40% 115%, rgb({rgb(s1)}) 0%, transparent 60%)")
        return {"--radius-sm": "10px", "--radius": "14px", "--radius-md": "16px", "--radius-lg": "22px",
                "--shadow-sm": f"0 2px 10px rgb({sh} / {k[0]})", "--shadow": f"0 8px 30px rgb({sh} / {k[1]})",
                "--shadow-lg": f"0 18px 50px rgb({sh} / {k[2]})",
                "--shadow-primary": "0 0 0 1px rgb(var(--primary) / 0.45), 0 8px 24px rgb(var(--primary) / 0.30)",
                "--shadow-primary-lg": "0 0 0 1px rgb(var(--primary) / 0.55), 0 14px 36px rgb(var(--primary) / 0.38)",
                **common, "--blur": "18px", "--page-bg": page}
    if sid == "turnup":  # fluid
        k = (0.35, 0.50, 0.60) if mode == "dark" else (0.08, 0.14, 0.20)
        page = (f"radial-gradient(70rem 40rem at 10% -15%, rgb({rgb(s1)}) 0%, transparent 70%), "
                f"radial-gradient(50rem 40rem at 100% 20%, rgb({rgb(s2)}) 0%, transparent 65%)")
        return {"--radius-sm": "8px", "--radius": "12px", "--radius-md": "14px", "--radius-lg": "20px",
                "--shadow-sm": f"0 1px 3px rgb(var(--shadow-color) / {k[0]})",
                "--shadow": f"0 8px 24px -10px rgb(var(--shadow-color) / {k[1]}), 0 1px 2px rgb(var(--shadow-color) / {k[0] / 2})",
                "--shadow-lg": f"0 20px 44px -16px rgb(var(--shadow-color) / {k[2]})",
                "--shadow-primary": "0 8px 22px -8px rgb(var(--primary) / 0.60)",
                "--shadow-primary-lg": "0 14px 32px -10px rgb(var(--primary) / 0.70)",
                **common, "--blur": "0px", "--page-bg": page}
    if sid == "pop":  # quiz-show: pill buttons on a solid dark 3D edge (see globals.css), chunky cards
        k = (0.45, 0.55, 0.65) if mode == "dark" else (0.10, 0.14, 0.18)
        s3 = v["page"][3]  # confetti: three soft glows in different colours
        page = (f"radial-gradient(38rem 28rem at 0% 0%, rgb({rgb(s1)}) 0%, transparent 70%), "
                f"radial-gradient(34rem 26rem at 100% 35%, rgb({rgb(s2)}) 0%, transparent 70%), "
                f"radial-gradient(40rem 30rem at 20% 100%, rgb({rgb(s3)}) 0%, transparent 70%)")
        return {"--radius-sm": "10px", "--radius": "14px", "--radius-md": "16px", "--radius-lg": "20px",
                "--shadow-sm": f"0 2px 0 rgb(var(--shadow-color) / {k[0]})",
                "--shadow": f"0 3px 0 rgb(var(--shadow-color) / {k[1]})",
                "--shadow-lg": f"0 5px 0 rgb(var(--shadow-color) / {k[2]})",
                "--shadow-primary": "0 3px 0 rgb(var(--shadow-color))",
                "--shadow-primary-lg": "0 5px 0 rgb(var(--shadow-color))",
                **common, "--blur": "0px", "--page-bg": page}
    # fluffy
    page = (f"radial-gradient(40rem 30rem at 10% 0%, rgb({rgb(s1)}) 0%, transparent 70%), "
            f"radial-gradient(40rem 30rem at 90% 30%, rgb({rgb(s2)}) 0%, transparent 70%)")
    return {"--radius-sm": "14px", "--radius": "20px", "--radius-md": "22px", "--radius-lg": "28px",
            "--shadow-sm": "0 4px 12px -4px rgb(var(--shadow-color) / 0.30)",
            "--shadow": "0 10px 28px -10px rgb(var(--shadow-color) / 0.45)",
            "--shadow-lg": "0 18px 40px -14px rgb(var(--shadow-color) / 0.50)",
            "--shadow-primary": "0 10px 24px -8px rgb(var(--primary) / 0.55)",
            "--shadow-primary-lg": "0 16px 32px -10px rgb(var(--primary) / 0.60)",
            **common, "--blur": "0px", "--page-bg": page}

for sid, s in S.items():
    modes = {}
    for m in ("dark", "light"):
        v = s[m]
        if "shadow" in v:
            shadow = v["shadow"]
        else:
            shadow = ("000000" if m == "dark" else ("BE3A79" if sid == "fluffy" else "1E2963"))
        surface = v.get("surface", v["card"])
        elevated = v.get("elevated") or (blend(v["card"], v["bg"], v["elevated_alpha"]) if sid == "fluffy" else v["card"])
        overlay = v.get("overlay", v["card"])
        modes[m] = {"--bg": rgb(v["bg"]), "--bg-surface": rgb(surface), "--bg-card": rgb(v["card"]),
                    "--bg-elevated": rgb(elevated), "--bg-overlay": rgb(overlay),
                    "--border": rgb(v["border"]), "--border-subtle": rgb(v["subtle"]), "--border-strong": rgb(v["border"]),
                    "--text": rgb(v["text"]), "--text-secondary": rgb(v["text2"]), "--text-muted": rgb(v["muted"]),
                    "--text-disabled": rgb(v["disabled"]), "--primary": rgb(v["primary"]), "--primary-hover": rgb(v["hover"]),
                    "--primary-light": rgb(v["plight"]), "--primary-muted": rgb(v["pmuted"]), "--on-primary": rgb(v["on"]),
                    "--shadow-color": rgb(shadow), **style_vars(sid, m, v)}
    themes[sid] = {"name": s["name"], "blurb": s["blurb"], "style": s["style"],
                   "swatch": {m: "#" + s[m]["primary"] for m in ("dark", "light")},
                   "chrome": {m: "#" + s[m]["bg"] for m in ("dark", "light")}, "modes": modes}

order = ["turnup", "pop", "sunset", "gold", "glass", "fluffy"]
data = json.dumps({k: themes[k] for k in order}, indent=2)
print(f'''// GENERATED by scripts/themes (see its README): edit the palettes there and regenerate.
// Colours were checked for WCAG contrast
// (body text >= 7:1, secondary/muted/accent text >= 4.5:1, button labels >= 4.5:1; for the
// translucent Glass theme against the panel blended over every part of the page gradient).
// The one exception: white button labels on Turnup's electric purple in dark mode (3.96:1), kept as the brand look.

export type ThemeMode = "light" | "dark";
export type ModePreference = ThemeMode | "system";
export type ThemeStyle = "fluid" | "pop" | "brutal" | "glass" | "fluffy";

export interface ThemeDef {{
  name: string;
  blurb: string;
  /** fluid: rounded, thin soft borders, diffuse shadows (the default); pop: quiz-show chunky,
   *  3D bottom edges, rounded bold type; brutal: hard borders + offset shadows; glass: frosted
   *  translucent panels; fluffy: soft pastel, very round, cloud shadows. */
  style: ThemeStyle;
  swatch: Record<ThemeMode, string>;
  /** Page background colour, used for the browser/OS chrome (meta theme-color). */
  chrome: Record<ThemeMode, string>;
  /** CSS custom properties set on <html>. */
  modes: Record<ThemeMode, Record<string, string>>;
}}

export const THEMES = {data} as const satisfies Record<string, ThemeDef>;

export type ThemeId = keyof typeof THEMES;
export const THEME_IDS = Object.keys(THEMES) as ThemeId[];
export const DEFAULT_THEME: ThemeId = "turnup";
export const DEFAULT_MODE: ModePreference = "dark";
export const MODE_PREFERENCES: ModePreference[] = ["light", "dark", "system"];

export function isThemeId(v: unknown): v is ThemeId {{
  return typeof v === "string" && v in THEMES;
}}

export function isModePreference(v: unknown): v is ModePreference {{
  return v === "light" || v === "dark" || v === "system";
}}

/** Account-synced form: "palette:mode", e.g. "sunset:system". */
export function encodePreference(theme: ThemeId, mode: ModePreference): string {{
  return `${{theme}}:${{mode}}`;
}}

export function decodePreference(value: string | null | undefined): {{ theme: ThemeId; mode: ModePreference }} | null {{
  if (!value) return null;
  const [theme, mode] = value.split(":");
  return isThemeId(theme) && isModePreference(mode) ? {{ theme, mode }} : null;
}}

export function systemPrefersDark(): boolean {{
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}}

export function resolveMode(mode: ModePreference): ThemeMode {{
  return mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
}}

/** Apply a theme to the page: CSS variables, light/dark classes, style attribute, and the
 *  browser/OS chrome colour. Safe to call repeatedly. */
export function applyTheme(theme: ThemeId, mode: ModePreference): void {{
  if (typeof document === "undefined") return;
  const def: ThemeDef = THEMES[theme] ?? THEMES[DEFAULT_THEME];
  const resolved = resolveMode(mode);
  const root = document.documentElement;
  for (const [name, value] of Object.entries(def.modes[resolved])) root.style.setProperty(name, value);
  root.classList.toggle("dark", resolved === "dark");
  root.classList.toggle("light", resolved === "light");
  root.dataset.theme = theme;
  root.dataset.style = def.style;
  root.style.colorScheme = resolved;
  let meta = document.querySelector('meta[name="theme-color"]:not([media])') as HTMLMetaElement | null;
  if (!meta) {{
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
  }}
  meta.content = def.chrome[resolved];
}}

/** Inline <head> script: applies the saved theme before first paint, so there's no flash of
 *  the default theme (works in the static Android export too). Reads the same localStorage
 *  entry the UI store writes, including the old {{theme: "dark"|"light"}} shape. */
export function themeBootScript(): string {{
  const themes = Object.fromEntries(
    Object.entries(THEMES).map(([id, t]) => [id, {{ s: t.style, c: t.chrome, m: t.modes }}]),
  );
  return `(function(){{try{{var T=${{JSON.stringify(themes)}};var st={{}};try{{st=(JSON.parse(localStorage.getItem('turnup-ui')||'{{}}').state)||{{}};}}catch(e){{}}
var id=T[st.palette]?st.palette:'${{DEFAULT_THEME}}';var mode=st.mode||st.theme||'${{DEFAULT_MODE}}';
if(mode==='system'){{mode=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}}
if(mode!=='light'&&mode!=='dark')mode='dark';var t=T[id],r=document.documentElement,v=t.m[mode];
for(var k in v)r.style.setProperty(k,v[k]);r.classList.add(mode);r.setAttribute('data-theme',id);r.setAttribute('data-style',t.s);r.style.colorScheme=mode;
}}catch(e){{document.documentElement.classList.add('dark');}}}})();`;
}}
''')
