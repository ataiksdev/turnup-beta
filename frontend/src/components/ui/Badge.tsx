import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

type Variant = "default" | "primary" | "success" | "warning" | "error" | "outline";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

const variants: Record<Variant, string> = {
  default:  "bg-bg-elevated text-text-secondary border border-border",
  primary:  "bg-primary/15 text-primary border border-primary/30",
  success:  "bg-success/15 text-success border border-success/30",
  warning:  "bg-warning/15 text-warning border border-warning/30",
  error:    "bg-error/15 text-error border border-error/30",
  outline:  "border border-border-strong text-text-secondary",
};

export function Badge({ variant = "default", className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium",
        variants[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
