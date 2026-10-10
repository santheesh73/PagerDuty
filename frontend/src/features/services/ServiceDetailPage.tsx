import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  Check,
  ChevronRight,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Pencil,
  Send,
  Trash2,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import type { Service, ServiceMode } from "@/api/types";
import { ModeBadge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader } from "@/components/Card";
import { Dialog } from "@/components/Dialog";
import { Field, Select } from "@/components/Field";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "@/components/States";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useDocumentTitle, useNow } from "@/lib/hooks";
import { hasRole, useMe } from "@/features/auth/hooks";
import { IncidentTable } from "@/features/incidents/components";
import { flattenPages, useIncidents } from "@/features/incidents/hooks";
import { ServiceFormDialog } from "./ServiceForm";
import { useDeleteService, useRotateKey, useService, useSetMode, useTestAlert } from "./hooks";

export function ServiceDetailPage() {
  const id = Number(useParams().id);
  const service = useService(id);
  const { data: me } = useMe();
  useDocumentTitle(service.data?.name ?? "Service");

  if (service.isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (service.isError)
    return <ErrorState error={service.error} onRetry={() => void service.refetch()} />;
  const data = service.data;
  const isAdmin = hasRole(me, data.team, "admin");
  const canRespond = hasRole(me, data.team, "responder");

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1 text-sm text-muted">
        <Link to="/services" className="hover:text-text">
          Services
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="text-text">{data.name}</span>
      </nav>
      <ModeBanner service={data} canEdit={isAdmin} />
      <Header service={data} isAdmin={isAdmin} canRespond={canRespond} />
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <RecentIncidents serviceId={data.id} />
        <div className="space-y-6">
          <ModeCard service={data} canEdit={isAdmin} />
          <IntegrationCard service={data} isAdmin={isAdmin} />
        </div>
      </div>
    </>
  );
}

function Header({
  service,
  isAdmin,
  canRespond,
}: {
  service: Service;
  isAdmin: boolean;
  canRespond: boolean;
}) {
  const testAlert = useTestAlert(service.id);
  const navigate = useNavigate();
  const remove = useDeleteService();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{service.name}</h1>
            <ModeBadge mode={service.mode} />
          </div>
          <p className="mt-1 text-muted">{service.description || "No description."}</p>
          <p className="mt-2 text-sm text-muted">
            Escalates via{" "}
            <Link
              to={`/escalation-policies/${service.escalation_policy}`}
              className="font-medium text-text hover:text-accent"
            >
              {service.escalation_policy_name}
            </Link>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canRespond && (
            <Button
              variant="primary"
              icon={<Send className="size-4" />}
              loading={testAlert.isPending}
              onClick={() =>
                testAlert.mutate(undefined, {
                  onSuccess: (result) =>
                    toast.success("Test alert sent", {
                      description:
                        service.mode === "maintenance"
                          ? "Folded into the maintenance incident — nobody was paged."
                          : service.mode === "debug"
                            ? "Debug mode: the pipeline ran, pages were recorded as dry runs."
                            : "The on-call responder is being paged.",
                      action: result.incident_id
                        ? {
                            label: "Open incident",
                            onClick: () => navigate(`/incidents/${result.incident_id}`),
                          }
                        : undefined,
                    }),
                })
              }
            >
              Send test alert
            </Button>
          )}
          {isAdmin && (
            <>
              <Button icon={<Pencil className="size-4" />} onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button
                variant="ghost"
                icon={<Trash2 className="size-4" />}
                onClick={() => setConfirmDelete(true)}
                aria-label="Delete service"
              />
            </>
          )}
        </div>
      </div>
      <ServiceFormDialog open={editing} onClose={() => setEditing(false)} service={service} />
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={`Delete ${service.name}?`}
        description="Its incidents and alerts are deleted too. Monitoring that still sends to its key will be rejected."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => remove.mutate(service.id, { onSuccess: () => navigate("/services") })}
            >
              Delete service
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">This can't be undone.</p>
      </Dialog>
    </Card>
  );
}

function ModeBanner({ service, canEdit }: { service: Service; canEdit: boolean }) {
  const now = useNow();
  const setMode = useSetMode(service.id);
  if (service.mode === "active") return null;
  const maintenance = service.mode === "maintenance";
  return (
    <div
      role="status"
      className={cn(
        "mb-4 flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm",
        maintenance
          ? "border-info/30 bg-info-soft text-info-fg"
          : "border-accent/30 bg-accent-soft text-accent",
      )}
    >
      <Wrench className="size-4 shrink-0" aria-hidden />
      <p className="flex-1">
        <strong className="font-semibold">
          {maintenance ? "Maintenance mode" : "Debug mode"}.
        </strong>{" "}
        {maintenance
          ? "Alerts are collected into one quiet incident and nobody is paged."
          : "Incidents and escalation run normally, but notifications are recorded as dry runs and never sent."}{" "}
        {service.mode_until
          ? `Returns to active ${formatRelative(service.mode_until, now)} (${formatDateTime(service.mode_until)}).`
          : "No end time set."}
      </p>
      {canEdit && (
        <Button
          size="sm"
          loading={setMode.isPending}
          onClick={() => setMode.mutate({ mode: "active" })}
        >
          End now
        </Button>
      )}
    </div>
  );
}

const DURATIONS = [
  { label: "30 minutes", minutes: 30 },
  { label: "1 hour", minutes: 60 },
  { label: "4 hours", minutes: 240 },
  { label: "24 hours", minutes: 1440 },
  { label: "Until I turn it off", minutes: 0 },
];

function ModeCard({ service, canEdit }: { service: Service; canEdit: boolean }) {
  const setMode = useSetMode(service.id);
  const [mode, setModeValue] = useState<ServiceMode>(
    service.mode === "active" ? "maintenance" : service.mode,
  );
  const [minutes, setMinutes] = useState(60);
  return (
    <Card>
      <CardHeader
        title="Mode"
        description="Silence a service during planned work, or test its pipeline without paging anyone."
      />
      <div className="space-y-3 p-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted">Current</span>
          <ModeBadge mode={service.mode} />
        </div>
        {canEdit ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Switch to">
                {(props) => (
                  <Select
                    {...props}
                    value={mode}
                    onChange={(e) => setModeValue(e.target.value as ServiceMode)}
                  >
                    <option value="maintenance">Maintenance</option>
                    <option value="debug">Debug (dry run)</option>
                    <option value="active">Active</option>
                  </Select>
                )}
              </Field>
              <Field label="For">
                {(props) => (
                  <Select
                    {...props}
                    disabled={mode === "active"}
                    value={minutes}
                    onChange={(e) => setMinutes(Number(e.target.value))}
                  >
                    {DURATIONS.map((d) => (
                      <option key={d.minutes} value={d.minutes}>
                        {d.label}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
            <Button
              className="w-full"
              loading={setMode.isPending}
              disabled={mode === service.mode && mode === "active"}
              onClick={() =>
                setMode.mutate({
                  mode,
                  until:
                    mode !== "active" && minutes
                      ? new Date(Date.now() + minutes * 60_000).toISOString()
                      : null,
                })
              }
            >
              Apply
            </Button>
          </>
        ) : (
          <p className="text-xs text-subtle">Only team admins can change the mode.</p>
        )}
      </div>
    </Card>
  );
}

function IntegrationCard({ service, isAdmin }: { service: Service; isAdmin: boolean }) {
  const rotate = useRotateKey(service.id);
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState<"key" | "curl" | null>(null);
  const [confirm, setConfirm] = useState(false);
  const key = service.integration_key;
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const curl = `curl -X POST ${origin}/api/v1/events/ \\
  -H 'Content-Type: application/json' \\
  -d '{
    "routing_key": "${key && revealed ? key : "<integration key>"}",
    "event_action": "trigger",
    "dedup_key": "disk-full/db-1",
    "payload": {
      "summary": "Disk 95% full on db-1",
      "severity": "critical",
      "source": "prometheus"
    }
  }'`;

  const copy = async (text: string, what: "key" | "curl") => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      toast.error("Couldn't copy to the clipboard");
    }
  };

  return (
    <Card>
      <CardHeader
        title="Events API"
        description="Send alerts here from Prometheus, Datadog, or anything that can POST JSON."
      />
      <div className="space-y-4 p-4">
        <div>
          <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-muted">
            <span className="inline-flex items-center gap-1.5">
              <KeyRound className="size-3.5" aria-hidden /> Integration key
            </span>
            {isAdmin && (
              <button
                type="button"
                className="text-accent hover:underline"
                onClick={() => setConfirm(true)}
              >
                Rotate
              </button>
            )}
          </div>
          {key ? (
            <div className="flex items-center gap-1 rounded-lg border border-border bg-surface-2 p-1 pl-3">
              <code className="min-w-0 flex-1 truncate font-mono text-xs">
                {revealed ? key : `${key.slice(0, 6)}${"•".repeat(20)}${key.slice(-4)}`}
              </code>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setRevealed((v) => !v)}
                aria-label={revealed ? "Hide key" : "Show key"}
                icon={revealed ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void copy(key, "key")}
                aria-label="Copy key"
                icon={
                  copied === "key" ? <Check className="size-3.5" /> : <Copy className="size-3.5" />
                }
              />
            </div>
          ) : (
            <p className="rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted">
              Only team admins can see the key.
            </p>
          )}
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-muted">
            <span>Example</span>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-accent hover:underline"
              onClick={() => void copy(curl, "curl")}
            >
              {copied === "curl" ? (
                <Check className="size-3.5" aria-hidden />
              ) : (
                <Copy className="size-3.5" aria-hidden />
              )}{" "}
              Copy
            </button>
          </div>
          <pre
            tabIndex={0}
            aria-label="Example Events API request"
            className="overflow-x-auto rounded-lg bg-[#0f1320] p-3 font-mono text-[11px] leading-relaxed text-[#d7dcf0]"
          >
            {curl}
          </pre>
          <p className="mt-2 text-xs text-subtle">
            Send <code className="font-mono">acknowledge</code> or{" "}
            <code className="font-mono">resolve</code> with the same{" "}
            <code className="font-mono">dedup_key</code> to close the loop from your monitoring.
          </p>
        </div>
      </div>
      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Rotate integration key?"
        description="The current key stops working immediately. Update your monitoring with the new one."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={rotate.isPending}
              onClick={() =>
                rotate.mutate(undefined, {
                  onSuccess: () => {
                    setConfirm(false);
                    setRevealed(true);
                  },
                })
              }
            >
              Rotate key
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          Alerts sent with the old key will be rejected with{" "}
          <code className="font-mono">invalid_routing_key</code>.
        </p>
      </Dialog>
    </Card>
  );
}

function RecentIncidents({ serviceId }: { serviceId: number }) {
  const query = useIncidents({ service: String(serviceId) }, { pageSize: 10 });
  const incidents = flattenPages(query.data).slice(0, 10);
  return (
    <section aria-labelledby="recent-incidents">
      <h2 id="recent-incidents" className="mb-3 text-sm font-semibold">
        Recent incidents
      </h2>
      {query.isPending ? (
        <SkeletonRows rows={4} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : incidents.length === 0 ? (
        <EmptyState title="No incidents yet">
          Send a test alert to watch it page, escalate and resolve.
        </EmptyState>
      ) : (
        <>
          <IncidentTable incidents={incidents} compact />
          <Link
            to={`/incidents?service=${serviceId}&tab=all`}
            className="mt-3 inline-block text-sm text-accent hover:underline"
          >
            View all incidents for this service
          </Link>
        </>
      )}
    </section>
  );
}
