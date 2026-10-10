import { Link } from "react-router";
import { CheckCircle2, PhoneCall, Siren } from "lucide-react";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader, PageHeader, Stat } from "@/components/Card";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "@/components/States";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import { useDocumentTitle } from "@/lib/hooks";
import { useMe } from "@/features/auth/hooks";
import { useAnalyticsSummary } from "@/features/analytics/hooks";
import { IncidentTable } from "@/features/incidents/components";
import { flattenPages, useIncidents } from "@/features/incidents/hooks";
import { useOnCalls } from "@/features/policies/hooks";

export function DashboardPage() {
  useDocumentTitle("Dashboard");
  const { data: me } = useMe();
  const open = useIncidents({ status: "triggered,acknowledged" }, { pageSize: 50 });
  const recent = useIncidents({}, { pageSize: 8 });
  const summary = useAnalyticsSummary({ days: 30 });
  const openIncidents = flattenPages(open.data);
  const counts = {
    triggered: openIncidents.filter((i) => i.status === "triggered").length,
    high: openIncidents.filter((i) => i.urgency === "high").length,
    low: openIncidents.filter((i) => i.urgency === "low").length,
  };
  const s = summary.data;

  return (
    <>
      <PageHeader
        title={`Good ${greeting()}, ${me?.name.split(" ")[0] ?? ""}`}
        description="What's on fire, who's holding the pager, and how fast the team is responding."
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[1.1fr_1.3fr_1fr_1fr_1fr]">
        <OpenCard loading={open.isPending} counts={counts} total={openIncidents.length} />
        <OnCallCard />
        <div className="grid grid-cols-3 gap-4 md:col-span-2 xl:contents">
          <Stat
            label="First response"
            emphasis
            loading={!s}
            value={formatDuration(s?.time_to_first_response_seconds)}
            hint="30-day average"
          />
          <Stat
            label="MTTA"
            loading={!s}
            value={formatDuration(s?.mtta_seconds)}
            hint="30-day average"
          />
          <Stat
            label="MTTR"
            loading={!s}
            value={formatDuration(s?.mttr_seconds)}
            hint="30-day average"
          />
        </div>
      </div>

      <section className="mt-8" aria-labelledby="open-heading">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="open-heading" className="text-sm font-semibold">
            Open incidents
          </h2>
          <Link to="/incidents" className="text-sm text-accent hover:underline">
            View all
          </Link>
        </div>
        {open.isPending ? (
          <SkeletonRows rows={3} />
        ) : open.isError ? (
          <ErrorState error={open.error} onRetry={() => void open.refetch()} />
        ) : openIncidents.length === 0 ? (
          <EmptyState
            icon={<CheckCircle2 />}
            title="All quiet"
            action={
              <Link to="/services">
                <Button variant="primary">Send a test alert</Button>
              </Link>
            }
          >
            Nothing is open. Send a test alert from a service to see paging end to end.
          </EmptyState>
        ) : (
          <IncidentTable incidents={openIncidents.slice(0, 8)} />
        )}
      </section>

      <section className="mt-8" aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="mb-3 text-sm font-semibold">
          Recent activity
        </h2>
        {recent.isPending ? (
          <SkeletonRows rows={3} />
        ) : recent.isError ? (
          <ErrorState error={recent.error} onRetry={() => void recent.refetch()} />
        ) : (
          <IncidentTable incidents={flattenPages(recent.data).slice(0, 8)} />
        )}
      </section>
    </>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
}

function OpenCard({
  loading,
  counts,
  total,
}: {
  loading: boolean;
  counts: { triggered: number; high: number; low: number };
  total: number;
}) {
  return (
    <Card className={cn("p-5", counts.triggered > 0 && "ring-1 ring-critical/40")}>
      <div className="flex items-center gap-2 text-xs font-medium text-muted">
        <Siren className="size-4" aria-hidden /> Open incidents
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-10 w-24" />
      ) : (
        <>
          <p className="tabular mt-2 text-4xl font-semibold tracking-tight">{total}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link to="/incidents?urgency=high">
              <Badge tone="critical" dot>
                {counts.high} high urgency
              </Badge>
            </Link>
            <Link to="/incidents?urgency=low">
              <Badge tone="neutral" dot>
                {counts.low} low urgency
              </Badge>
            </Link>
            {counts.triggered > 0 && (
              <Link to="/incidents?tab=triggered">
                <Badge tone="warning">{counts.triggered} unacknowledged</Badge>
              </Link>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function OnCallCard() {
  const { data: me } = useMe();
  const oncalls = useOnCalls();
  const mine = (oncalls.data ?? []).flatMap((p) =>
    p.levels
      .filter((level) => level.oncall.some((entry) => entry.user?.id === me?.id))
      .map((level) => ({
        policy: p.policy,
        level: level.level,
        via: level.oncall.find((e) => e.user?.id === me?.id)?.schedule?.name,
      })),
  );
  const onCall = mine.length > 0;
  return (
    <Card className={cn("p-5", onCall && "border-accent/40 bg-accent-soft/40")}>
      <CardHeader
        className="-mx-5 -mt-5 mb-3 border-b-0 pb-0"
        title={
          <span className="inline-flex items-center gap-2 text-xs font-medium text-muted">
            <PhoneCall className="size-4" aria-hidden /> Your on-call
          </span>
        }
      />
      {oncalls.isPending ? (
        <Skeleton className="h-16" />
      ) : onCall ? (
        <>
          <p className="text-lg font-semibold">You're on call</p>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {mine.map((m) => (
              <li key={`${m.policy.id}-${m.level}`}>
                <Link
                  to={`/escalation-policies/${m.policy.id}`}
                  className="font-medium text-text hover:text-accent"
                >
                  {m.policy.name}
                </Link>{" "}
                · level {m.level + 1}
                {m.via && ` via ${m.via}`}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <p className="text-lg font-semibold">You're off call</p>
          <p className="mt-1 text-sm text-muted">
            Enjoy it. Check the{" "}
            <Link to="/schedules" className="text-accent hover:underline">
              schedules
            </Link>{" "}
            for your next shift.
          </p>
        </>
      )}
    </Card>
  );
}
