"use client";
import { cn } from "@/lib/utils";
import { Bell, ChevronLeft } from "lucide-react";
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
        <ThemeToggle />
        {!back && user && (
          <Link href={`/profile/${user.username}`} aria-label={`${user.full_name}'s profile`}>
            <Avatar src={user.avatar_url} name={user.full_name} size="sm" verified={user.is_verified} />
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
