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
  primary:   "bg-primary hover:bg-primary-hover text-white shadow-glow-sm active:scale-95",
  secondary: "bg-bg-elevated hover:bg-bg-overlay text-text border border-border",
  ghost:     "hover:bg-bg-elevated text-text-secondary hover:text-text",
  outline:   "border border-primary text-primary hover:bg-primary hover:text-white",
  danger:    "bg-error hover:bg-red-600 text-white",
};

const sizes: Record<Size, string> = {
  xs: "h-7  px-3  text-xs  rounded-xl gap-1",
  sm: "h-8  px-4  text-sm  rounded-xl gap-1.5",
  md: "h-10 px-5  text-sm  rounded-2xl gap-2",
  lg: "h-12 px-6  text-base rounded-2xl gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, fullWidth, className, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center font-medium transition-all duration-150 select-none",
        "disabled:opacity-50 disabled:cursor-not-allowed",
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
