import { Link } from "react-router";
import {
  ArrowUpCircle,
  Bell,
  BellOff,
  CheckCircle2,
  CircleAlert,
  CircleDot,
  Hammer,
  Layers,
  MessageSquare,
  RotateCcw,
  Siren,
  UserRoundCog,
  UserX,
  Wrench,
} from "lucide-react";
import type { EscalationSnapshot, Incident, IncidentDetail, IncidentEvent } from "@/api/types";
import { Avatar, Person } from "@/components/Avatar";
import { StatusBadge, UrgencyBadge, type Tone } from "@/components/Badge";
import { cn } from "@/lib/cn";
import { formatDateTime, formatDuration, formatRelative } from "@/lib/format";
import { useNow } from "@/lib/hooks";

// --- list ---------------------------------------------------------------------------------

export function IncidentTable({
  incidents,
  compact,
}: {
  incidents: Incident[];
  compact?: boolean;
}) {
  const now = useNow();
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
      <table className="w-full table-fixed text-sm">
        <caption className="sr-only">Incidents</caption>
        <thead className="border-b border-border bg-surface-2/60 text-left text-xs text-muted">
          <tr>
            <th scope="col" className="w-32 px-4 py-2.5 font-medium">
              Status
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Incident
            </th>
            {!compact && (
              <th scope="col" className="hidden w-40 px-4 py-2.5 font-medium md:table-cell">
                Service
              </th>
            )}
            <th
              scope="col"
              className={cn("hidden w-44 px-4 py-2.5 font-medium", !compact && "lg:table-cell")}
            >
              Assignee
            </th>
            <th scope="col" className="w-28 px-4 py-2.5 text-right font-medium">
              Triggered
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {incidents.map((incident) => (
            <tr key={incident.id} className="group relative hover:bg-surface-2/60">
              <td className="px-4 py-3 align-top">
                <StatusBadge status={incident.status} />
              </td>
              <td className="min-w-0 px-4 py-3">
                <div className="flex min-w-0 items-center gap-2">
                  <UrgencyBadge urgency={incident.urgency} />
                  <Link
                    to={`/incidents/${incident.id}`}
                    className="truncate font-medium text-text after:absolute after:inset-0 focus-visible:outline-none group-hover:text-accent"
                  >
                    {incident.title}
                  </Link>
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted">
                  <span className="tabular font-mono">#{incident.number}</span>
                  {incident.alert_count > 1 && <span>· {incident.alert_count} alerts</span>}
                  {incident.is_maintenance && <span>· maintenance</span>}
                  <span className="md:hidden">· {incident.service.name}</span>
                </div>
              </td>
              {!compact && (
                <td className="hidden truncate px-4 py-3 text-muted md:table-cell">
                  {incident.service.name}
                </td>
              )}
              <td className={cn("hidden px-4 py-3", !compact && "lg:table-cell")}>
                <Person user={incident.assignee} />
              </td>
              <td
                className="tabular px-4 py-3 text-right text-xs text-muted"
                title={formatDateTime(incident.triggered_at)}
              >
                {formatRelative(incident.triggered_at, now)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- timeline -----------------------------------------------------------------------------

const EVENT_STYLE: Record<string, { icon: typeof Siren; tone: Tone; label: string }> = {
  triggered: { icon: Siren, tone: "critical", label: "Triggered" },
  alert_attached: { icon: Layers, tone: "neutral", label: "Alert attached" },
  acknowledged: { icon: CircleDot, tone: "warning", label: "Acknowledged" },
  unacknowledged: { icon: RotateCcw, tone: "critical", label: "Unacknowledged" },
  resolved: { icon: CheckCircle2, tone: "good", label: "Resolved" },
  reassigned: { icon: UserRoundCog, tone: "info", label: "Reassigned" },
  escalated: { icon: ArrowUpCircle, tone: "critical", label: "Escalated" },
  manual_escalated: { icon: ArrowUpCircle, tone: "critical", label: "Escalated manually" },
  no_responder: { icon: UserX, tone: "warning", label: "Nobody on call" },
  escalation_exhausted: { icon: CircleAlert, tone: "critical", label: "Escalation exhausted" },
  note_added: { icon: MessageSquare, tone: "accent", label: "Note" },
  notified: { icon: Bell, tone: "neutral", label: "Notified" },
  notification_failed: { icon: BellOff, tone: "critical", label: "Notification failed" },
  maintenance_started: { icon: Wrench, tone: "info", label: "Maintenance started" },
  maintenance_ended: { icon: Hammer, tone: "good", label: "Maintenance ended" },
};

const TONE_RING: Record<Tone, string> = {
  critical: "bg-critical-soft text-critical-fg",
  warning: "bg-warning-soft text-warning-fg",
  good: "bg-good-soft text-good-fg",
  info: "bg-info-soft text-info-fg",
  neutral: "bg-surface-2 text-muted",
  accent: "bg-accent-soft text-accent",
};

export function Timeline({
  events,
  showDeliveries,
}: {
  events: IncidentEvent[];
  showDeliveries: boolean;
}) {
  const now = useNow();
  const visible = showDeliveries ? events : events.filter((e) => e.type !== "notified");
  return (
    <ol className="relative space-y-1" aria-label="Incident timeline">
      {visible.map((event, index) => {
        const style = EVENT_STYLE[event.type] ?? EVENT_STYLE.notified!;
        const Icon = style.icon;
        const quiet = event.type === "notified" || event.type === "alert_attached";
        const dryRun = (event.data as { dry_run?: boolean } | undefined)?.dry_run;
        return (
          <li key={event.id} className="relative flex gap-3 pb-3">
            {index < visible.length - 1 && (
              <span className="absolute top-8 bottom-0 left-[15px] w-px bg-border" aria-hidden />
            )}
            <span
              className={cn(
                "relative z-10 mt-0.5 grid size-8 shrink-0 place-items-center rounded-full ring-4 ring-surface",
                TONE_RING[style.tone],
              )}
            >
              <Icon className="size-4" aria-hidden />
            </span>
            <div className={cn("min-w-0 flex-1 pt-1", quiet && "text-muted")}>
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className={cn("font-medium", quiet ? "text-muted" : "text-text")}>
                  {style.label}
                </span>
                {dryRun && (
                  <span className="rounded bg-accent-soft px-1.5 text-[10px] font-semibold tracking-wide text-accent uppercase">
                    dry run
                  </span>
                )}
                <span className="text-xs text-subtle">
                  {event.actor ? `by ${event.actor.name}` : "by Pulse"} ·{" "}
                  <time dateTime={event.created_at} title={formatDateTime(event.created_at)}>
                    {formatRelative(event.created_at, now)}
                  </time>
                </span>
              </div>
              {event.message && event.type === "note_added" ? (
                <p className="mt-1.5 rounded-lg border border-border bg-surface-2/60 px-3 py-2 whitespace-pre-wrap text-text">
                  {event.message}
                </p>
              ) : (
                event.message &&
                event.message !== style.label && (
                  <p className="mt-0.5 text-sm text-muted">{event.message}</p>
                )
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

// --- escalation ---------------------------------------------------------------------------

export function EscalationPath({ incident }: { incident: IncidentDetail }) {
  const now = useNow(1_000);
  const snapshot = incident.escalation_snapshot as unknown as EscalationSnapshot;
  const rules = snapshot.rules ?? [];
  const due = incident.next_escalation_at ? new Date(incident.next_escalation_at).getTime() : null;
  const remaining = due ? Math.max(0, (due - now) / 1000) : null;
  const live = incident.status === "triggered";

  if (rules.length === 0) {
    return (
      <p className="text-sm text-muted">
        This service's policy had no levels when the incident opened.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-2 text-xs text-muted">
        <span>
          Policy <span className="font-medium text-text">{snapshot.policy_name}</span> · frozen at
          open
        </span>
        {snapshot.num_loops > 0 && (
          <span>
            Loop {incident.escalation_loop + 1} of {snapshot.num_loops + 1}
          </span>
        )}
      </div>
      {live && remaining !== null && (
        <div className="flex items-center justify-between rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical-fg">
          <span>Escalates to the next level in</span>
          <span className="tabular font-semibold" aria-live="off">
            {formatDuration(remaining)}
          </span>
        </div>
      )}
      <ol className="space-y-2">
        {rules.map((rule) => {
          const current =
            rule.level === incident.escalation_level && incident.status !== "resolved";
          const passed = rule.level < incident.escalation_level || incident.escalation_loop > 0;
          return (
            <li
              key={rule.level}
              aria-current={current ? "step" : undefined}
              className={cn(
                "rounded-lg border px-3 py-2.5",
                current ? "border-accent/50 bg-accent-soft/50" : "border-border",
              )}
            >
              <div className="flex items-center justify-between text-xs">
                <span className={cn("font-semibold", current ? "text-accent" : "text-muted")}>
                  Level {rule.level + 1}
                  {current && " · current"}
                  {!current && passed && " · paged"}
                </span>
                <span className="text-subtle">escalate after {rule.delay_minutes} min</span>
              </div>
              <ul className="mt-1.5 space-y-1">
                {rule.targets.map((target) => (
                  <li
                    key={`${target.type}-${target.id}`}
                    className="flex items-center gap-2 text-sm"
                  >
                    {target.type === "user" ? (
                      <Avatar user={{ id: target.id, name: target.name ?? "?" }} size="sm" />
                    ) : (
                      <span className="grid size-6 place-items-center rounded-full bg-surface-2 text-muted">
                        <Layers className="size-3.5" aria-hidden />
                      </span>
                    )}
                    <span className="truncate">{target.name}</span>
                    {target.type === "schedule" && (
                      <span className="text-xs text-subtle">on-call</span>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function ResponseTimes({ incident }: { incident: IncidentDetail }) {
  const since = (iso: string | null | undefined) =>
    iso
      ? formatDuration((new Date(iso).getTime() - new Date(incident.triggered_at).getTime()) / 1000)
      : null;
  const rows: [string, string | null | undefined, string | null][] = [
    ["Triggered", incident.triggered_at, null],
    ["First response", incident.first_response_at, since(incident.first_response_at)],
    ["Acknowledged", incident.acknowledged_at, since(incident.acknowledged_at)],
    ["Resolved", incident.resolved_at, since(incident.resolved_at)],
  ];
  return (
    <dl className="divide-y divide-border">
      {rows.map(([label, at, elapsed]) => (
        <div key={label} className="flex items-baseline justify-between gap-3 py-2 text-sm">
          <dt className="text-muted">{label}</dt>
          <dd className="text-right">
            {at ? (
              <>
                <span className="tabular">{formatDateTime(at)}</span>
                {elapsed && <span className="tabular ml-2 text-xs text-subtle">+{elapsed}</span>}
              </>
            ) : (
              <span className="text-subtle">—</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
