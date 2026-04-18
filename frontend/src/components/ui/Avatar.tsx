import { cn, getInitials } from "@/lib/utils";
import Image from "next/image";

interface AvatarProps {
  src?: string | null;
  name: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  className?: string;
  verified?: boolean;
}

const sizes = {
  xs: { container: "w-6 h-6",   text: "text-[9px]",  badge: "w-2.5 h-2.5 text-[6px]" },
  sm: { container: "w-8 h-8",   text: "text-xs",      badge: "w-3 h-3 text-[7px]" },
  md: { container: "w-10 h-10", text: "text-sm",      badge: "w-3.5 h-3.5 text-[8px]" },
  lg: { container: "w-14 h-14", text: "text-base",    badge: "w-4 h-4 text-[9px]" },
  xl: { container: "w-20 h-20", text: "text-xl",      badge: "w-5 h-5 text-[10px]" },
};

export function Avatar({ src, name, size = "md", className, verified }: AvatarProps) {
  const s = sizes[size];
  return (
    <div className={cn("relative shrink-0", className)}>
      <div className={cn("rounded-full overflow-hidden bg-bg-elevated border-2 border-border", s.container)}>
        {src ? (
          <Image src={src} alt={name} fill className="object-cover" sizes="80px" />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-primary to-primary-hover">
            <span className={cn("font-semibold text-white", s.text)}>
              {getInitials(name)}
            </span>
          </div>
        )}
      </div>
      {verified && (
        <span className={cn(
          "absolute -bottom-0.5 -right-0.5 rounded-full bg-primary flex items-center justify-center",
          s.badge,
        )}>
          ✓
        </span>
      )}
    </div>
  );
}
