import { useSearchParams } from "react-router";
import { Card, CardHeader, PageHeader, Stat } from "@/components/Card";
import { Select } from "@/components/Field";
import { EmptyState, ErrorState, Skeleton } from "@/components/States";
import { formatDuration, formatPercent } from "@/lib/format";
import { useDocumentTitle } from "@/lib/hooks";
import { useServices } from "@/features/services/hooks";
import { Legend, ResponseTrend, SeriesTable, VolumeChart } from "./charts";
import { useAnalyticsSeries, useAnalyticsSummary } from "./hooks";

const RANGES = [7, 30, 60, 90];

export function AnalyticsPage() {
  useDocumentTitle("Analytics");
  const [params, setParams] = useSearchParams();
  const days = RANGES.includes(Number(params.get("days"))) ? Number(params.get("days")) : 30;
  const service = params.get("service") ?? undefined;
  const summary = useAnalyticsSummary({ days, service });
  const series = useAnalyticsSeries({ days, service });
  const services = useServices();
  const set = (key: string, value: string) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  const s = summary.data;
  const maxAlerts = Math.max(1, ...(s?.noisy_services.map((n) => n.alerts) ?? [1]));

  return (
    <>
      <PageHeader
        title="Analytics"
        description="How fast the team responds, and where the noise comes from. Maintenance incidents are excluded."
        actions={
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filters">
            <Select
              aria-label="Date range"
              className="w-40"
              value={days}
              onChange={(e) => set("days", e.target.value)}
            >
              {RANGES.map((d) => (
                <option key={d} value={d}>
                  Last {d} days
                </option>
              ))}
            </Select>
            <Select
              aria-label="Service"
              className="w-44"
              value={service ?? ""}
              onChange={(e) => set("service", e.target.value)}
            >
              <option value="">All services</option>
              {services.data?.map((svc) => (
                <option key={svc.id} value={svc.id}>
                  {svc.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />

      {summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
          <div className="col-span-2 md:col-span-1">
            <Stat
              label="Time to first response"
              emphasis
              loading={!s}
              value={formatDuration(s?.time_to_first_response_seconds)}
              hint="Trigger → first human action"
            />
          </div>
          <Stat
            label="MTTA"
            loading={!s}
            value={formatDuration(s?.mtta_seconds)}
            hint="Mean time to acknowledge"
          />
          <Stat
            label="MTTR"
            loading={!s}
            value={formatDuration(s?.mttr_seconds)}
            hint="Mean time to resolve"
          />
          <Stat
            label="Incidents"
            loading={!s}
            value={s?.incidents ?? "—"}
            hint={s ? `${s.by_urgency.high} high · ${s.by_urgency.low} low` : undefined}
          />
          <Stat
            label="Escalation rate"
            loading={!s}
            value={formatPercent(s?.escalation_rate)}
            hint="Needed more than level 1"
          />
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Response times per day"
            description="Average minutes from trigger"
            action={
              <Legend
                items={[
                  { label: "First response", color: "var(--series-1)", kind: "line" },
                  { label: "MTTA", color: "var(--series-2)", kind: "line" },
                ]}
              />
            }
          />
          <div className="p-4">
            {series.isPending ? (
              <Skeleton className="h-64" />
            ) : series.isError ? (
              <ErrorState error={series.error} onRetry={() => void series.refetch()} />
            ) : series.data.every((p) => p.incidents === 0) ? (
              <EmptyState title="No incidents in this range">
                Widen the date range or send a test alert.
              </EmptyState>
            ) : (
              <>
                <ResponseTrend points={series.data} />
                <SeriesTable points={series.data} />
              </>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader
            title="Incident volume"
            description="Incidents per day by urgency"
            action={
              <Legend
                items={[
                  { label: "High urgency", color: "var(--series-1)" },
                  { label: "Low urgency", color: "var(--series-2)" },
                ]}
              />
            }
          />
          <div className="p-4">
            {series.isPending ? (
              <Skeleton className="h-64" />
            ) : series.isError ? null : (
              <VolumeChart points={series.data} />
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader
          title="Noisiest services"
          description="Top 5 by alert count — candidates for tuning"
        />
        {!s ? (
          <div className="p-4">
            <Skeleton className="h-32" />
          </div>
        ) : s.noisy_services.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No alerts in this range" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">
                  Service
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Alerts
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Incidents
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Alerts / incident
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {s.noisy_services.map((row) => (
                <tr key={row.id}>
                  <td className="px-4 py-2.5 font-medium">{row.name}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-3">
                      <div className="h-2 w-40 max-w-full rounded-full bg-surface-2" aria-hidden>
                        <div
                          className="h-2 rounded-full bg-series-1"
                          style={{ width: `${(row.alerts / maxAlerts) * 100}%` }}
                        />
                      </div>
                      <span className="tabular">{row.alerts}</span>
                    </div>
                  </td>
                  <td className="tabular px-4 py-2.5 text-right">{row.incidents}</td>
                  <td className="tabular px-4 py-2.5 text-right text-muted">
                    {(row.alerts / Math.max(1, row.incidents)).toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
