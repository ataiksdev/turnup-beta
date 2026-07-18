"use client";
import { cn, displayName } from "@/lib/utils";
import { Bell, ChevronLeft, LayoutDashboard, Shield } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { Avatar } from "@/components/ui/Avatar";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

interface TopBarProps {
  title?: string;
  back?: boolean;
  transparent?: boolean;
  actions?: React.ReactNode;
  className?: string;
}

export function TopBar({ title, back, transparent, actions, className }: TopBarProps) {
  const router = useRouter();
  const { user } = useAuthStore();
  const isOrganizer = user?.role === "organizer";
  const isAdmin = user?.role === "admin";

  return (
    <header
      role="banner"
      className={cn(
        "sticky top-0 z-40 flex items-center justify-between h-14 px-4 safe-top",
        transparent
          ? "bg-transparent"
          : "bg-bg-surface border-b-2 border-border",
        className,
      )}
    >
      {/* Left */}
      <div className="flex items-center gap-2 min-w-0">
        {back ? (
          <button
            onClick={() => router.back()}
            aria-label="Go back"
            className="p-2 -ml-2 rounded hover:bg-bg-elevated transition-colors"
          >
            <ChevronLeft size={20} className="text-text" aria-hidden />
          </button>
        ) : (
          <Link href="/" aria-label="Turnup home" className="flex items-center gap-1.5">
            <span className="text-xl font-black text-primary tracking-tight">turnup</span>
          </Link>
        )}
        {title && (
          <h1 className="text-base font-bold text-text truncate">{title}</h1>
        )}
      </div>

      {/* Right */}
      <div className="flex items-center gap-1">
        {actions}
        {/* Admin shortcut */}
        {!back && isAdmin && (
          <Link
            href="/admin"
            aria-label="Switch to admin panel"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded border-2 border-red-300 bg-red-100 hover:bg-red-200 transition-colors"
          >
            <Shield size={13} className="text-red-700" aria-hidden />
            <span className="text-[10px] font-black text-red-700 uppercase tracking-wider hidden xs:inline">
              Admin
            </span>
          </Link>
        )}
        {/* Organizer shortcut — visible to organizers in the attendee layout */}
        {!back && isOrganizer && (
          <Link
            href="/organizer/dashboard"
            aria-label="Switch to organizer view"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded border-2 border-primary/40 bg-primary/10 hover:bg-primary/20 transition-colors"
          >
            <LayoutDashboard size={13} className="text-primary" aria-hidden />
            <span className="text-[10px] font-black text-primary uppercase tracking-wider hidden xs:inline">
              Organizer
            </span>
          </Link>
        )}
        <ThemeToggle />
        {!back && user && (
          <Link href={`/profile/${user.username}`} aria-label={`${displayName(user)}'s profile`}>
            <Avatar src={user.avatar_url} name={displayName(user)} size="sm" verified={user.is_verified} />
          </Link>
        )}
        {!back && (
          <Link
            href="/activity"
            aria-label="Notifications"
            className="relative p-2 rounded hover:bg-bg-elevated transition-colors"
          >
            <Bell size={20} className="text-text-secondary" aria-hidden />
          </Link>
        )}
      </div>
    </header>
  );
}
