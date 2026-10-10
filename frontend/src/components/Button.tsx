import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Spinner } from "./States";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "good" | "warning";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent-hover shadow-card",
  secondary:
    "bg-surface text-text border border-border hover:bg-surface-2 hover:border-border-strong shadow-card",
  ghost: "text-muted hover:text-text hover:bg-surface-2",
  danger: "bg-critical text-white hover:brightness-110 shadow-card",
  good: "bg-good text-white hover:brightness-110 shadow-card",
  warning: "bg-warning text-white hover:brightness-110 shadow-card",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-2.5 text-xs gap-1.5",
  md: "h-9 px-3.5 text-sm gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  shortcut?: string;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading,
    icon,
    shortcut,
    className,
    children,
    disabled,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      aria-keyshortcuts={shortcut}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg font-medium whitespace-nowrap",
        "transition-[background,color,border,filter] duration-150",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="size-3.5" /> : icon}
      {children}
      {shortcut && (
        <kbd className="ml-0.5 hidden rounded border border-current/20 px-1 font-mono text-[10px] leading-4 opacity-70 sm:inline">
          {shortcut.toUpperCase()}
        </kbd>
      )}
    </button>
  );
});
