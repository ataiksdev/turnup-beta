"use client";
import { cn } from "@/lib/utils";
import { Compass, Home, Search, Users, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { useQuery } from "@tanstack/react-query";
import { socialApi } from "@/lib/api";

const navItems = [
  { href: "/",             icon: Home,    label: "Home" },
  { href: "/search",       icon: Search,  label: "Search" },
  { href: "/communities",  icon: Users,   label: "Communities" },
  { href: "/activity",     icon: Compass, label: "Activity" },
  { href: "/profile",      icon: User,    label: "Profile" },
];

export function BottomNav() {
  const pathname = usePathname();
  const { user, token } = useAuthStore();

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => socialApi.notifications(token!),
    enabled: !!token,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const unreadCount = notifications?.filter((n) => !n.is_read).length ?? 0;

  return (
    <nav
      aria-label="Main navigation"
      className="fixed bottom-0 inset-x-0 z-50 bg-bg-surface border-t-2 border-border safe-bottom"
    >
      <div className="flex items-center justify-around h-16 max-w-lg mx-auto px-2">
        {navItems.map(({ href, icon: Icon, label }) => {
          const resolvedHref = href === "/profile" && user
            ? `/profile/${user.username}`
            : href;
          const isActive =
            pathname === resolvedHref ||
            (href !== "/" && pathname.startsWith(href) && href !== "/profile");
          const showBadge = href === "/activity" && unreadCount > 0;

          return (
            <Link
              key={href}
              href={resolvedHref}
              aria-label={label}
              aria-current={isActive ? "page" : undefined}
              className="flex flex-col items-center justify-center gap-0.5 flex-1 h-full group"
            >
              <div className={cn(
                "relative p-1.5 rounded transition-all duration-150",
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
                {showBadge && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] rounded-full bg-primary text-white text-[9px] font-black flex items-center justify-center px-0.5 border border-bg-surface">
                    {unreadCount > 9 ? "9+" : unreadCount}
                  </span>
                )}
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
      </div>
    </nav>
  );
}
