#!/usr/bin/env node
// Removes the admin/moderator portal from the static export before it's packaged into the
// Capacitor mobile app. The admin portal is web-only by design (security/segregation) — it must
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

function stripFlatAdminFiles(dir) {
  // Top-level exports like admin.html / admin.txt sitting alongside the admin/ directory.
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir)) {
    if (entry === "admin.html" || entry === "admin.txt") {
      rm(path.join(dir, entry));
    }
  }
}

if (!fs.existsSync(OUT_DIR)) {
  console.error(`[strip-admin] ${OUT_DIR} does not exist — run "next build" first.`);
  process.exit(1);
}

rm(path.join(OUT_DIR, "admin"));
stripFlatAdminFiles(OUT_DIR);

const chunksDir = path.join(OUT_DIR, "_next", "static", "chunks", "app", "(admin)");
rm(chunksDir);

console.log("[strip-admin] done.");
