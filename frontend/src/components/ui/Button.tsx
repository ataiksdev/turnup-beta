import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "outline" | "danger";
type Size = "xs" | "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
}

const variants: Record<Variant, string> = {
  primary:
    "bg-primary text-white border-2 border-border font-bold " +
    "shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg " +
    "active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
  secondary:
    "bg-bg-card text-text border-2 border-border font-bold " +
    "shadow-brutal-sm hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal " +
    "active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
  ghost:
    "text-text-secondary hover:text-text hover:bg-bg-elevated border border-border-subtle font-medium",
  outline:
    "bg-transparent text-primary border-2 border-primary font-bold " +
    "shadow-brutal-primary hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[5px_5px_0_#F97316] " +
    "active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
  danger:
    "bg-error text-white border-2 border-border font-bold " +
    "shadow-brutal hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-brutal-lg " +
    "active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
};

const sizes: Record<Size, string> = {
  xs: "h-7  px-3  text-xs  rounded gap-1",
  sm: "h-8  px-4  text-sm  rounded gap-1.5",
  md: "h-10 px-5  text-sm  rounded gap-2",
  lg: "h-12 px-6  text-base rounded gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, fullWidth, className, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center transition-all duration-100 select-none",
        "disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none disabled:translate-x-0 disabled:translate-y-0",
        variants[variant],
        sizes[size],
        fullWidth && "w-full",
        className,
      )}
      {...props}
    >
      {loading && <Loader2 className="animate-spin" size={14} />}
      {children}
    </button>
  ),
);

Button.displayName = "Button";
