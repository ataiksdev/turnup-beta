import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

type Variant = "default" | "primary" | "success" | "warning" | "error" | "outline";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

const variants: Record<Variant, string> = {
  default:  "bg-bg-elevated text-text-secondary border-border",
  primary:  "bg-primary text-white border-primary",
  success:  "bg-success text-white border-success",
  warning:  "bg-warning text-black border-warning",
  error:    "bg-error text-white border-error",
  outline:  "bg-transparent border-border text-text-secondary",
};

export function Badge({ variant = "default", className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wide border",
        variants[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
