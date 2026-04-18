import { cn } from "@/lib/utils";
import { InputHTMLAttributes, forwardRef, ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: ReactNode;
  iconRight?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, iconRight, className, ...props }, ref) => (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label className="text-xs font-bold text-text-secondary uppercase tracking-wide">{label}</label>
      )}
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted">
            {icon}
          </span>
        )}
        <input
          ref={ref}
          className={cn(
            "w-full h-11 bg-bg-card border-2 border-border rounded",
            "px-4 text-sm text-text placeholder:text-text-muted font-medium",
            "focus:outline-none focus:border-primary focus:shadow-brutal-primary",
            "transition-all duration-100",
            icon && "pl-10",
            iconRight && "pr-10",
            error && "border-error focus:border-error focus:shadow-[3px_3px_0_#EF4444]",
            className,
          )}
          {...props}
        />
        {iconRight && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted">
            {iconRight}
          </span>
        )}
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
    </div>
  ),
);

Input.displayName = "Input";
