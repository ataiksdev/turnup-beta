"use client";
import { cn } from "@/lib/utils";
import { BarChart2, CalendarPlus, LayoutDashboard, ArrowLeftRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";

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
                isActive ? "bg-primary text-white" : "group-hover:bg-bg-elevated",
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

export default function OrganizerLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-bg pb-20 max-w-lg mx-auto">
      {children}
      <OrganizerBottomNav />
    </div>
  );
}
