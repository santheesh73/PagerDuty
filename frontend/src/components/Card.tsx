import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-xl border border-border bg-surface shadow-card", className)}
      {...rest}
    />
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-3 border-b border-border px-4 py-3",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-text">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium text-muted">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight text-text">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  emphasis,
  loading,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  emphasis?: boolean;
  loading?: boolean;
}) {
  return (
    <Card className={cn("p-4", emphasis && "ring-1 ring-accent/30")}>
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted">{label}</div>
      {loading ? (
        <div className="skeleton mt-2 h-7 w-24 rounded" aria-hidden />
      ) : (
        <div
          className={cn(
            "tabular mt-1 font-semibold tracking-tight",
            emphasis ? "text-3xl" : "text-2xl",
          )}
        >
          {value}
        </div>
      )}
      {hint && <div className="mt-1 text-xs text-subtle">{hint}</div>}
    </Card>
  );
}
