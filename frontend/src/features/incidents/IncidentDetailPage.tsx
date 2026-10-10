import { useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import {
  ArrowUpCircle,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  RotateCcw,
  UserRoundCog,
} from "lucide-react";
import type { IncidentAction } from "@/api/types";
import { Person } from "@/components/Avatar";
import { Badge, StatusBadge, UrgencyBadge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader } from "@/components/Card";
import { Dialog } from "@/components/Dialog";
import { Field, Select, Textarea } from "@/components/Field";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "@/components/States";
import { Tabs } from "@/components/Tabs";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useDocumentTitle, useNow, useShortcuts } from "@/lib/hooks";
import { useTeamMembers } from "@/features/services/hooks";
import { EscalationPath, ResponseTimes, Timeline } from "./components";
import {
  useAddNote,
  useAlerts,
  useIncident,
  useIncidentAction,
  useReassign,
  useTimeline,
} from "./hooks";

const NOTE_LIMIT = 5000;

export function IncidentDetailPage() {
  const id = Number(useParams().id);
  const incident = useIncident(id);
  useDocumentTitle(incident.data ? `#${incident.data.number} ${incident.data.title}` : "Incident");

  if (incident.isPending) return <DetailSkeleton />;
  if (incident.isError)
    return <ErrorState error={incident.error} onRetry={() => void incident.refetch()} />;
  const data = incident.data;

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1 text-sm text-muted">
        <Link to="/incidents" className="hover:text-text">
          Incidents
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="tabular font-mono text-text">#{data.number}</span>
      </nav>

      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={data.status} />
            <UrgencyBadge urgency={data.urgency} />
            {data.is_maintenance && <Badge tone="info">Maintenance</Badge>}
            {data.service.mode === "debug" && <Badge tone="accent">Debug · dry-run pages</Badge>}
          </div>
          <ActionBar
            incidentId={id}
            allowed={data.allowed_actions as IncidentAction[]}
            teamId={data.service.team}
          />
        </div>
        <h1 className="mt-3 text-xl font-semibold tracking-tight text-balance">{data.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <Link
            to={`/services/${data.service.id}`}
            className="font-medium text-text hover:text-accent"
          >
            {data.service.name}
          </Link>
          <span title={formatDateTime(data.triggered_at)}>
            Triggered {formatRelative(data.triggered_at)}
          </span>
          <span>{data.alert_count === 1 ? "1 alert" : `${data.alert_count} alerts`}</span>
          <span className="inline-flex items-center gap-1.5">
            Assignee <Person user={data.assignee} />
          </span>
        </div>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <ActivityPanel incidentId={id} canNote={data.allowed_actions.includes("add_note")} />
        <div className="space-y-6">
          <Card>
            <CardHeader title="Escalation" description="The path this incident follows" />
            <div className="p-4">
              <EscalationPath incident={data} />
            </div>
          </Card>
          <Card>
            <CardHeader title="Response" />
            <div className="px-4 pb-2">
              <ResponseTimes incident={data} />
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function ActionBar({
  incidentId,
  allowed,
  teamId,
}: {
  incidentId: number;
  allowed: IncidentAction[];
  teamId: number;
}) {
  const action = useIncidentAction(incidentId);
  const [reassignOpen, setReassignOpen] = useState(false);
  const can = (name: IncidentAction) => allowed.includes(name);
  const run = (name: "acknowledge" | "unacknowledge" | "resolve" | "escalate") => () => {
    if (can(name) && !action.isPending) action.mutate(name);
  };
  const pending = action.isPending ? action.variables : undefined;

  // Keyboard shortcuts only for actions you can take right now.
  const allowedKey = allowed.join(",");
  const busy = action.isPending;
  const { mutate } = action;
  const shortcuts = useMemo(() => {
    const ok = new Set(allowedKey.split(","));
    const bind = (name: "acknowledge" | "unacknowledge" | "resolve" | "escalate") =>
      ok.has(name) && !busy ? () => mutate(name) : undefined;
    return {
      a: bind("acknowledge"),
      u: bind("unacknowledge"),
      r: bind("resolve"),
      e: bind("escalate"),
    };
  }, [allowedKey, busy, mutate]);
  useShortcuts(shortcuts);

  if (allowed.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Incident actions">
      {can("acknowledge") && (
        <Button
          variant="warning"
          icon={<CircleDot className="size-4" />}
          shortcut="a"
          loading={pending === "acknowledge"}
          onClick={run("acknowledge")}
        >
          Acknowledge
        </Button>
      )}
      {can("unacknowledge") && (
        <Button
          icon={<RotateCcw className="size-4" />}
          shortcut="u"
          loading={pending === "unacknowledge"}
          onClick={run("unacknowledge")}
        >
          Unacknowledge
        </Button>
      )}
      {can("resolve") && (
        <Button
          variant="good"
          icon={<CheckCircle2 className="size-4" />}
          shortcut="r"
          loading={pending === "resolve"}
          onClick={run("resolve")}
        >
          Resolve
        </Button>
      )}
      {can("escalate") && (
        <Button
          icon={<ArrowUpCircle className="size-4" />}
          shortcut="e"
          loading={pending === "escalate"}
          onClick={run("escalate")}
        >
          Escalate
        </Button>
      )}
      {can("reassign") && (
        <Button icon={<UserRoundCog className="size-4" />} onClick={() => setReassignOpen(true)}>
          Reassign
        </Button>
      )}
      <ReassignDialog
        incidentId={incidentId}
        teamId={teamId}
        open={reassignOpen}
        onClose={() => setReassignOpen(false)}
      />
    </div>
  );
}

function ReassignDialog({
  incidentId,
  teamId,
  open,
  onClose,
}: {
  incidentId: number;
  teamId: number;
  open: boolean;
  onClose: () => void;
}) {
  const members = useTeamMembers(open ? teamId : undefined);
  const reassign = useReassign(incidentId);
  const [assignee, setAssignee] = useState("");
  const eligible = members.data?.filter((m) => m.role !== "viewer") ?? [];
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Reassign incident"
      description="The new assignee is paged right away and the escalation timer restarts."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!assignee}
            loading={reassign.isPending}
            onClick={() => reassign.mutate(Number(assignee), { onSuccess: onClose })}
          >
            Reassign
          </Button>
        </>
      }
    >
      <Field label="New assignee">
        {(props) => (
          <Select
            {...props}
            data-autofocus
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
          >
            <option value="">Choose a responder…</option>
            {eligible.map((m) => (
              <option key={m.user.id} value={m.user.id}>
                {m.user.name} ({m.role})
              </option>
            ))}
          </Select>
        )}
      </Field>
    </Dialog>
  );
}

function ActivityPanel({ incidentId, canNote }: { incidentId: number; canNote: boolean }) {
  const [tab, setTab] = useState<"timeline" | "alerts">("timeline");
  const [deliveries, setDeliveries] = useState(false);
  const timeline = useTimeline(incidentId);
  const alerts = useAlerts(incidentId, tab === "alerts");

  return (
    <Card>
      <div className="flex items-center justify-between gap-2 px-4 pt-2">
        <Tabs
          label="Incident activity"
          className="flex-1 border-b-0"
          items={[
            { key: "timeline", label: "Timeline" },
            { key: "alerts", label: "Alerts" },
          ]}
          value={tab}
          onChange={setTab}
        />
        {tab === "timeline" && (
          <label className="flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              className="accent-[var(--accent)]"
              checked={deliveries}
              onChange={(e) => setDeliveries(e.target.checked)}
            />
            Show deliveries
          </label>
        )}
      </div>
      <div className="border-t border-border p-4">
        {tab === "timeline" ? (
          <>
            {canNote && <NoteComposer incidentId={incidentId} />}
            {timeline.isPending ? (
              <SkeletonRows rows={4} />
            ) : timeline.isError ? (
              <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} />
            ) : (
              <Timeline events={timeline.data.results} showDeliveries={deliveries} />
            )}
          </>
        ) : alerts.isPending ? (
          <SkeletonRows rows={3} />
        ) : alerts.isError ? (
          <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
        ) : alerts.data.results.length === 0 ? (
          <EmptyState title="No alerts attached" />
        ) : (
          <AlertList alerts={alerts.data.results} />
        )}
      </div>
    </Card>
  );
}

function AlertList({
  alerts,
}: {
  alerts: {
    id: number;
    summary: string;
    severity: string;
    source: string;
    status: string;
    received_at: string;
    dedup_key: string;
    payload: unknown;
  }[];
}) {
  const now = useNow();
  return (
    <ul className="divide-y divide-border">
      {alerts.map((alert) => (
        <li key={alert.id} className="py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              tone={
                alert.severity === "critical" || alert.severity === "error"
                  ? "critical"
                  : alert.severity === "warning"
                    ? "warning"
                    : "info"
              }
            >
              {alert.severity}
            </Badge>
            <span className="font-medium">{alert.summary}</span>
          </div>
          <div className="mt-1 text-xs text-muted">
            {alert.source || "unknown source"} · {alert.status} ·{" "}
            {formatRelative(alert.received_at, now)} · key{" "}
            <code className="font-mono">{alert.dedup_key}</code>
          </div>
          <details className="mt-1 text-xs">
            <summary className="cursor-pointer text-subtle hover:text-muted">Payload</summary>
            <pre className="mt-1 overflow-x-auto rounded-lg bg-surface-2 p-2 font-mono text-[11px]">
              {JSON.stringify(alert.payload, null, 2)}
            </pre>
          </details>
        </li>
      ))}
    </ul>
  );
}

function NoteComposer({ incidentId }: { incidentId: number }) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const addNote = useAddNote(incidentId);
  const over = text.length > NOTE_LIMIT;
  useShortcuts(useMemo(() => ({ n: () => ref.current?.focus() }), []));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || over) return;
    addNote.mutate(text.trim(), { onSuccess: () => setText("") });
  };
  return (
    <form onSubmit={submit} className="mb-5">
      <label htmlFor="note" className="sr-only">
        Add a note
      </label>
      <Textarea
        id="note"
        ref={ref}
        placeholder="Add a note for the timeline… (press N)"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
        }}
        aria-invalid={over || undefined}
        rows={2}
      />
      <div className="mt-2 flex items-center justify-between">
        <span className={over ? "text-xs text-critical-fg" : "text-xs text-subtle"}>
          {text.length.toLocaleString()} / {NOTE_LIMIT.toLocaleString()}
        </span>
        <Button
          type="submit"
          size="sm"
          variant="primary"
          disabled={!text.trim() || over}
          loading={addNote.isPending}
        >
          Add note
        </Button>
      </div>
    </form>
  );
}

function DetailSkeleton() {
  return (
    <div role="status" aria-label="Loading incident">
      <Skeleton className="mb-3 h-4 w-40" />
      <Skeleton className="h-32 w-full rounded-xl" />
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Skeleton className="h-96 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    </div>
  );
}
