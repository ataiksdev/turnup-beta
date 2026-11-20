import type { Metadata, Viewport } from "next";
import { Inter, Nunito } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { SkipNav } from "@/components/layout/SkipNav";
import { PWASetup } from "@/components/layout/PWASetup";
import { themeBootScript } from "@/lib/themes";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
// Rounded, bold type for the Game Night theme (only downloaded when that theme is on).
const nunito = Nunito({ subsets: ["latin"], variable: "--font-pop", weight: ["500", "700", "800", "900"], preload: false });

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
    { media: "(prefers-color-scheme: dark)",  color: "#0C0A12" },
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
        <SkipNav />
        <Providers>
          {children}
          <PWASetup />
        </Providers>
      </body>
    </html>
  );
}
