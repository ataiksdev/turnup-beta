"use client";
import { useEffect } from "react";

const WORD = "turnup";
const MIN_MS = 1600; // long enough for the logo animation to play once

/**
 * Android app only (rendered by the root layout in the static export). The splash is in the
 * page's HTML and styled by the bundled stylesheet, so it shows from the very first paint,
 * offline too, before any JavaScript runs. Once the app has started (this effect runs) and the
 * animation has played, it fades out. If JavaScript never starts, a CSS fallback hides it
 * after a few seconds so the page underneath is still usable.
 */
export function AppSplash() {
  useEffect(() => {
    const el = document.getElementById("app-splash");
    if (!el) return;
    const wait = Math.max(0, MIN_MS - performance.now());
    const t1 = setTimeout(() => { el.dataset.state = "out"; }, wait);
    const t2 = setTimeout(() => { el.dataset.state = "gone"; }, wait + 450);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  return (
    <div id="app-splash" aria-hidden="true" data-state="in">
      <div className="app-splash-inner">
        <div className="app-splash-word">
          {WORD.split("").map((ch, i) => (
            <span key={i} style={{ "--i": i } as React.CSSProperties}>{ch}</span>
          ))}
        </div>
        <div className="app-splash-bars">
          {[0, 1, 2, 3, 4].map((i) => <span key={i} style={{ "--i": i } as React.CSSProperties} />)}
        </div>
        <p className="app-splash-tagline">vibes on demand</p>
      </div>
    </div>
  );
}
