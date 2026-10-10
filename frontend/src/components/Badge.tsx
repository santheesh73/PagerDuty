import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import type { IncidentStatus, ServiceMode } from "@/api/types";

export type Tone = "critical" | "warning" | "good" | "info" | "neutral" | "accent";

const tones: Record<Tone, string> = {
  critical: "bg-critical-soft text-critical-fg ring-critical/25",
  warning: "bg-warning-soft text-warning-fg ring-warning/25",
  good: "bg-good-soft text-good-fg ring-good/25",
  info: "bg-info-soft text-info-fg ring-info/25",
  neutral: "bg-neutral-soft text-muted ring-border-strong/40",
  accent: "bg-accent-soft text-accent ring-accent/25",
};

const dots: Record<Tone, string> = {
  critical: "bg-critical",
  warning: "bg-warning",
  good: "bg-good",
  info: "bg-info",
  neutral: "bg-subtle",
  accent: "bg-accent",
};

export function Badge({
  tone = "neutral",
  dot,
  pulse,
  children,
  className,
}: {
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {dot && (
        <span className="relative flex size-1.5" aria-hidden>
          {pulse && (
            <span
              className={cn(
                "absolute inline-flex size-full animate-ping rounded-full opacity-60 motion-reduce:hidden",
                dots[tone],
              )}
            />
          )}
          <span className={cn("relative inline-flex size-1.5 rounded-full", dots[tone])} />
        </span>
      )}
      {children}
    </span>
  );
}

const STATUS: Record<IncidentStatus, { tone: Tone; label: string }> = {
  triggered: { tone: "critical", label: "Triggered" },
  acknowledged: { tone: "warning", label: "Acknowledged" },
  resolved: { tone: "good", label: "Resolved" },
};

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const { tone, label } = STATUS[status];
  return (
    <Badge tone={tone} dot pulse={status === "triggered"}>
      {label}
    </Badge>
  );
}

export function UrgencyBadge({ urgency }: { urgency: string }) {
  return urgency === "high" ? (
    <Badge tone="critical" className="uppercase tracking-wide text-[10px]">
      High
    </Badge>
  ) : (
    <Badge tone="neutral" className="uppercase tracking-wide text-[10px]">
      Low
    </Badge>
  );
}

const MODES: Record<ServiceMode, { tone: Tone; label: string }> = {
  active: { tone: "good", label: "Active" },
  maintenance: { tone: "info", label: "Maintenance" },
  debug: { tone: "accent", label: "Debug" },
};

export function ModeBadge({ mode }: { mode: ServiceMode }) {
  const { tone, label } = MODES[mode];
  return (
    <Badge tone={tone} dot>
      {label}
    </Badge>
  );
}
