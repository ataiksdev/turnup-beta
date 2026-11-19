"use client";
import { cn } from "@/lib/utils";
import { BarChart2, CalendarPlus, LayoutDashboard, ArrowLeftRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { useState } from "react";
import { apiErrorMessage, authApi, organizerApi } from "@/lib/api";
import { Button } from "@/components/ui/Button";

const navItems = [
  { href: "/organizer/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/organizer/events",    icon: BarChart2,        label: "Events"    },
  { href: "/organizer/create",    icon: CalendarPlus,     label: "Create"    },
];

function OrganizerBottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Organizer navigation"
      className="fixed bottom-0 inset-x-0 z-50 bg-bg-surface border-t-2 border-border safe-bottom"
    >
      <div className="flex items-center justify-around h-16 max-w-lg mx-auto px-2">
        {navItems.map(({ href, icon: Icon, label }) => {
          const isActive = pathname === href || pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              aria-label={label}
              aria-current={isActive ? "page" : undefined}
              className="flex flex-col items-center justify-center gap-0.5 flex-1 h-full group"
            >
              <div className={cn(
                "p-1.5 rounded transition-all duration-150",
                isActive ? "bg-primary text-on-primary" : "group-hover:bg-bg-elevated",
              )}>
                <Icon
                  size={20}
                  strokeWidth={isActive ? 2.5 : 1.8}
                  aria-hidden="true"
                  className={cn(
                    "transition-colors duration-150",
                    isActive ? "text-white" : "text-text-muted group-hover:text-text-secondary",
                  )}
                />
              </div>
              <span className={cn(
                "text-[10px] font-bold uppercase tracking-wide transition-colors duration-150",
                isActive ? "text-primary" : "text-text-muted",
              )}>
                {label}
              </span>
            </Link>
          );
        })}

        {/* Fan View toggle — switches to attendee layout */}
        <Link
          href="/"
          aria-label="Switch to fan view"
          className="flex flex-col items-center justify-center gap-0.5 flex-1 h-full group"
        >
          <div className="p-1.5 rounded transition-all duration-150 group-hover:bg-bg-elevated">
            <ArrowLeftRight
              size={20}
              strokeWidth={1.8}
              aria-hidden="true"
              className="text-text-muted group-hover:text-text-secondary transition-colors duration-150"
            />
          </div>
          <span className="text-[10px] font-bold uppercase tracking-wide text-text-muted">
            Fan View
          </span>
        </Link>
      </div>
    </nav>
  );
}

const CAN_ORGANIZE = ["organizer", "admin", "moderator"];

/** Shown instead of the organizer screens to someone who isn't an organizer yet (e.g. they
 *  picked "Host events" at sign-up but left before finishing setup), rather than letting them
 *  fill in a whole event that the server would then refuse. */
function BecomeOrganizer() {
  const { token, setUser } = useAuthStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function become() {
    if (!token) return;
    setBusy(true); setError("");
    try {
      await organizerApi.become(token, {});
      setUser(await authApi.me(token));
    } catch (e) {
      setError(apiErrorMessage(e, "Couldn't switch your account. Please try again."));
    } finally { setBusy(false); }
  }
  return (
    <div className="flex flex-col items-center justify-center text-center gap-4 px-6 py-24">
      <CalendarPlus size={36} className="text-primary" aria-hidden />
      <h1 className="text-xl font-black text-text">Host events on Turnup</h1>
      <p className="text-sm text-text-secondary">Turn on organizer tools to create events, sell tickets and check guests in. You can add your organizer profile later.</p>
      <Button size="lg" loading={busy} onClick={become}>Become an organizer</Button>
      {error && <p className="text-xs text-error">{error}</p>}
      <Link href="/" className="text-xs font-bold text-text-muted underline">Not now</Link>
    </div>
  );
}

export default function OrganizerLayout({ children }: { children: React.ReactNode }) {
  const { user, hasHydrated } = useAuthStore();
  const pathname = usePathname();
  // Individual event pages are also used by co-hosts and venue teams; the API checks access.
  const ownScreens = !/^\/organizer\/(events|series)\/(?!$)/.test(pathname);
  const blocked = hasHydrated && !!user && ownScreens && !CAN_ORGANIZE.includes(user.role ?? "");
  return (
    <div className="min-h-screen bg-bg pb-20 max-w-lg mx-auto">
      {blocked ? <BecomeOrganizer /> : children}
      <OrganizerBottomNav />
    </div>
  );
}
