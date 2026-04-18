import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { SkipNav } from "@/components/layout/SkipNav";
import { PWASetup } from "@/components/layout/PWASetup";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

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
    { media: "(prefers-color-scheme: dark)",  color: "#09090B" },
    { media: "(prefers-color-scheme: light)", color: "#FAFAFA" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // No class here — ThemeScript sets it before paint to prevent FOUC
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Prevent flash of wrong theme — dark is default, only apply .light if stored */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=JSON.parse(localStorage.getItem('turnup-ui')||'{}');var t=(s&&s.state&&s.state.theme)||'dark';if(t==='light'){document.documentElement.classList.add('light');}else{document.documentElement.classList.add('dark');}}catch(e){document.documentElement.classList.add('dark');}})();`,
          }}
        />
      </head>
      <body className={`${inter.variable} font-sans antialiased`}>
        <SkipNav />
        <Providers>
          {children}
          <PWASetup />
        </Providers>
      </body>
    </html>
  );
}
