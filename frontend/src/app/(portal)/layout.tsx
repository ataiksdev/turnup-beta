"use client";
import { ArrowLeftRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { Button } from "@/components/ui/Button";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

/** Venue portal and agent portal: web-only (removed from the Android build by
 *  scripts/strip-admin.js), wider layout for desktop use. */
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const { token, hasHydrated } = useAuthStore();
  const pathname = usePathname();
  const section = pathname.startsWith("/agent") ? "Agent" : "Venue portal";
  return (
    <div className="min-h-screen bg-bg">
      <header className="sticky top-0 z-40 h-14 px-4 flex items-center gap-3 bg-bg-surface border-b-2 border-border">
        <Link href={section === "Agent" ? "/agent" : "/venue"} className="text-xl font-black text-primary tracking-tight">turnup</Link>
        <span className="text-[10px] font-black uppercase tracking-widest text-text-muted">{section}</span>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <Link href="/" className="flex items-center gap-1.5 px-2 py-1 text-xs font-bold text-text-secondary hover:text-text">
            <ArrowLeftRight size={14} aria-hidden /> App
          </Link>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-6">
        {!hasHydrated ? null : token ? children : (
          <div className="max-w-sm mx-auto text-center space-y-3 py-16">
            <p className="text-sm text-text">Log in to continue.</p>
            <Link href={`/login?next=${encodeURIComponent(pathname)}`}><Button>Log in</Button></Link>
          </div>
        )}
      </main>
    </div>
  );
}
