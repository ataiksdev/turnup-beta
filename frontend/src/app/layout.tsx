import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "./providers";
import { SkipNav } from "@/components/layout/SkipNav";
import { PWASetup } from "@/components/layout/PWASetup";
import { themeBootScript } from "@/lib/themes";
import { AppSplash } from "@/components/layout/AppSplash";

// The Android app (static export) gets the animated splash; the website doesn't.
const IS_APP = process.env.NEXT_PUBLIC_STATIC_EXPORT === "true";

// Fonts ship with the app (npm @fontsource-variable/*, SIL Open Font License) instead of being
// fetched from Google Fonts at build time, which made builds fail whenever that download did.
// Variable fonts: one file covers every weight.
const inter = localFont({
  src: "../../node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
  variable: "--font-inter", weight: "100 900", display: "swap",
});
// Rounded, bold type for the Game Night theme (only downloaded when that theme is on).
const nunito = localFont({
  src: "../../node_modules/@fontsource-variable/nunito/files/nunito-latin-wght-normal.woff2",
  variable: "--font-pop", weight: "200 1000", display: "swap", preload: false,
});

export const metadata: Metadata = {
  title: { default: "Turnup", template: "%s · Turnup" },
  description: "Discover events, connect with people, and never miss out.",
  manifest: "/manifest.json",
  icons: {
    icon: [
      { url: "/icon-192.svg", type: "image/svg+xml" },
    ],
    apple: "/icon-192.svg",
  },
  openGraph: {
    type: "website",
    siteName: "Turnup",
    title: "Turnup – Event Discovery",
    description: "Discover events, connect with people, and never miss out.",
  },
  twitter: {
    card: "summary_large_image",
    title: "Turnup – Event Discovery",
    description: "Discover events, connect with people, and never miss out.",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Turnup",
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: [
    { media: "(prefers-color-scheme: dark)",  color: "#000000" },
    { media: "(prefers-color-scheme: light)", color: "#F7F5FB" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // No class here — ThemeScript sets it before paint to prevent FOUC
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Apply the saved theme (palette + light/dark/system) before first paint, so the
            default theme never flashes. Generated from src/lib/themes.ts. */}
        <script dangerouslySetInnerHTML={{ __html: themeBootScript() }} />
      </head>
      <body className={`${inter.variable} ${nunito.variable} font-sans antialiased`}>
        {IS_APP && <AppSplash />}
        <SkipNav />
        <Providers>
          {children}
          <PWASetup />
        </Providers>
      </body>
    </html>
  );
}
