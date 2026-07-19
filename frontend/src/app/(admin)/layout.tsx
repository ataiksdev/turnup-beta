"use client";
import { useEffect } from "react";
import { cn } from "@/lib/utils";
import { LayoutDashboard, Users, CalendarDays, Tag, ShoppingBag, ArrowLeftRight, CalendarPlus, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";

// Pages under (admin) that moderators may view — everything else is admin-only.
const MODERATOR_PATHS = ["/admin/events/new", "/admin/events/ai-new"];
const isAdminOnlyPath = (pathname: string) =>
  !MODERATOR_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

const adminNavItems = [
  { href: "/admin",            icon: LayoutDashboard, label: "Overview"   },
  { href: "/admin/users",      icon: Users,           label: "Users"      },
  { href: "/admin/events",     icon: CalendarDays,    label: "Events"     },
  { href: "/admin/categories", icon: Tag,             label: "Categories" },
  { href: "/admin/orders",     icon: ShoppingBag,     label: "Orders"     },
];

const moderatorNavItems = [
  { href: "/admin/events/new",    icon: CalendarPlus, label: "Create"  },
  { href: "/admin/events/ai-new", icon: Sparkles,      label: "AI Draft" },
];

function AdminBottomNav({ role }: { role: string }) {
  const pathname = usePathname();
  const navItems = role === "admin" ? adminNavItems : moderatorNavItems;
  return (
    <nav aria-label="Admin navigation" className="fixed bottom-0 inset-x-0 z-50 bg-bg-surface border-t-2 border-border safe-bottom">
      <div className="flex items-center justify-around h-16 max-w-lg mx-auto px-2">
        {navItems.map(({ href, icon: Icon, label }) => {
          const isActive = href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
          return (
            <Link key={href} href={href} aria-label={label} aria-current={isActive ? "page" : undefined}
              className="flex flex-col items-center justify-center gap-0.5 flex-1 h-full group">
              <div className={cn("p-1.5 rounded transition-all duration-150",
                isActive ? "bg-primary text-white" : "group-hover:bg-bg-elevated")}>
                <Icon size={20} strokeWidth={isActive ? 2.5 : 1.8} aria-hidden="true"
                  className={cn("transition-colors duration-150",
                    isActive ? "text-white" : "text-text-muted group-hover:text-text-secondary")} />
              </div>
              <span className={cn("text-[10px] font-bold uppercase tracking-wide transition-colors duration-150",
                isActive ? "text-primary" : "text-text-muted")}>
                {label}
              </span>
            </Link>
          );
        })}
        <Link href="/" aria-label="Exit admin" className="flex flex-col items-center justify-center gap-0.5 flex-1 h-full group">
          <div className="p-1.5 rounded transition-all duration-150 group-hover:bg-bg-elevated">
            <ArrowLeftRight size={20} strokeWidth={1.8} aria-hidden="true" className="text-text-muted group-hover:text-text-secondary transition-colors duration-150" />
          </div>
          <span className="text-[10px] font-bold uppercase tracking-wide text-text-muted">Exit</span>
        </Link>
      </div>
    </nav>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  const pathname = usePathname();
  const router = useRouter();

  const isModerator = user?.role === "moderator";
  const shouldBounce = isModerator && isAdminOnlyPath(pathname);

  useEffect(() => {
    if (shouldBounce) router.replace("/admin/events/new");
  }, [shouldBounce, router]);

  if (!user || (user.role !== "admin" && user.role !== "moderator")) return null;
  if (shouldBounce) return null;

  return (
    <div className="min-h-screen bg-bg pb-20 max-w-lg mx-auto">
      {children}
      <AdminBottomNav role={user.role} />
    </div>
  );
}
