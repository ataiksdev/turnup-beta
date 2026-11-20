#!/usr/bin/env node
// Removes the web-only portals from the static export before it's packaged into the Capacitor
// mobile app: the admin/moderator portal, and the venue portal and agent portal (venue
// marketplace, docs/venues-spec.md). They're web-only by design (security/segregation) and must
// never ship inside the Android/iOS app bundle. The regular web deploy runs `next build` directly
// and keeps this content; only the Capacitor pipeline runs this script.
const fs = require("fs");
const path = require("path");

const OUT_DIR = path.join(__dirname, "..", "out");

function rm(targetPath) {
  if (fs.existsSync(targetPath)) {
    fs.rmSync(targetPath, { recursive: true, force: true });
    console.log(`[strip-admin] removed ${path.relative(OUT_DIR, targetPath)}`);
  }
}

const WEB_ONLY = ["admin", "venue", "agent"];

function stripFlatAdminFiles(dir) {
  // Top-level exports like admin.html / admin.txt sitting alongside the admin/ directory.
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir)) {
    if (WEB_ONLY.some((name) => entry === `${name}.html` || entry === `${name}.txt`)) {
      rm(path.join(dir, entry));
    }
  }
}

if (!fs.existsSync(OUT_DIR)) {
  console.error(`[strip-admin] ${OUT_DIR} does not exist — run "next build" first.`);
  process.exit(1);
}

for (const name of WEB_ONLY) rm(path.join(OUT_DIR, name));
stripFlatAdminFiles(OUT_DIR);

for (const group of ["(admin)", "(portal)"]) {
  rm(path.join(OUT_DIR, "_next", "static", "chunks", "app", group));
}

// Placeholder copies of the dynamic pages (/events/__placeholder.html, ...): Next.js 16.3+
// requires a static export to produce at least one page per dynamic route, and the app opens
// those screens through its /…/view?id= pages instead (see src/lib/staticParams.ts).
const PLACEHOLDER = "__placeholder";
let placeholders = 0;
function stripPlaceholders(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.name === PLACEHOLDER || entry.name.startsWith(`${PLACEHOLDER}.`)) {
      fs.rmSync(full, { recursive: true, force: true });
      placeholders++;
    } else if (entry.isDirectory() && entry.name !== "_next") {
      stripPlaceholders(full);
    }
  }
}
stripPlaceholders(OUT_DIR);
console.log(`[strip-admin] removed ${placeholders} placeholder page file(s)`);

console.log("[strip-admin] done.");
