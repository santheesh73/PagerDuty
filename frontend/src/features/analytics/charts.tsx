import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DayPoint } from "@/api/types";
import { formatDuration } from "@/lib/format";

const axis = { stroke: "var(--subtle)", fontSize: 11, tickLine: false, axisLine: false } as const;
const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en", { month: "short", day: "numeric" });
/** The bits of Recharts' tooltip props we use; the row's data object is in payload[0].payload. */
interface TipProps {
  active?: boolean;
  label?: string | number;
  payload?: readonly { payload?: unknown }[];
}
const row = <T,>(props: TipProps) => props.payload?.[0]?.payload as T | undefined;

const minutes = (seconds: number | null | undefined) =>
  seconds === null || seconds === undefined ? null : Math.round((seconds / 60) * 10) / 10;

export function Legend({
  items,
}: {
  items: { label: string; color: string; kind?: "line" | "box" }[];
}) {
  return (
    <ul className="flex flex-wrap gap-4 text-xs text-muted" aria-label="Legend">
      {items.map((item) => (
        <li key={item.label} className="inline-flex items-center gap-1.5">
          {item.kind === "line" ? (
            <span
              className="h-0.5 w-4 rounded-full"
              style={{ background: item.color }}
              aria-hidden
            />
          ) : (
            <span className="size-2.5 rounded-sm" style={{ background: item.color }} aria-hidden />
          )}
          {item.label}
        </li>
      ))}
    </ul>
  );
}

function TooltipCard({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: ReactNode; color: string }[];
}) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-pop">
      <p className="mb-1 font-medium text-text">{title}</p>
      {rows.map((row) => (
        <p key={row.label} className="flex items-center gap-2 text-muted">
          <span className="size-2 rounded-full" style={{ background: row.color }} aria-hidden />
          {row.label}
          <span className="tabular ml-auto pl-3 font-medium text-text">{row.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Time to first response and MTTA per day, in minutes (one axis, one unit). */
export function ResponseTrend({ points }: { points: DayPoint[] }) {
  const data = points.map((p) => ({
    date: p.date,
    ttfr: minutes(p.time_to_first_response_seconds),
    mtta: minutes(p.mtta_seconds),
  }));
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={24} {...axis} />
          <YAxis {...axis} tickFormatter={(v: number) => `${v}m`} allowDecimals={false} />
          <Tooltip
            cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
            content={(props: TipProps) => {
              const point = row<{ ttfr: number | null; mtta: number | null }>(props);
              if (!props.active || !point) return null;
              return (
                <TooltipCard
                  title={shortDate(String(props.label))}
                  rows={[
                    {
                      label: "First response",
                      value: formatDuration(point.ttfr === null ? null : point.ttfr * 60),
                      color: "var(--series-1)",
                    },
                    {
                      label: "MTTA",
                      value: formatDuration(point.mtta === null ? null : point.mtta * 60),
                      color: "var(--series-2)",
                    },
                  ]}
                />
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="ttfr"
            name="Time to first response"
            stroke="var(--series-1)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="mtta"
            name="MTTA"
            stroke="var(--series-2)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Incidents per day, stacked by urgency. */
export function VolumeChart({ points }: { points: DayPoint[] }) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={points}
          margin={{ top: 8, right: 12, bottom: 0, left: -20 }}
          barCategoryGap="20%"
        >
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="date" tickFormatter={shortDate} minTickGap={24} {...axis} />
          <YAxis {...axis} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            content={(props: TipProps) => {
              const point = row<DayPoint>(props);
              if (!props.active || !point) return null;
              return (
                <TooltipCard
                  title={shortDate(String(props.label))}
                  rows={[
                    { label: "High urgency", value: point.high, color: "var(--series-1)" },
                    { label: "Low urgency", value: point.low, color: "var(--series-2)" },
                  ]}
                />
              );
            }}
          />
          {/* A surface-coloured stroke is the 2px gap between stacked segments. */}
          <Bar
            dataKey="high"
            name="High urgency"
            stackId="u"
            fill="var(--series-1)"
            stroke="var(--surface)"
            strokeWidth={2}
            maxBarSize={24}
            isAnimationActive={false}
          />
          <Bar
            dataKey="low"
            name="Low urgency"
            stackId="u"
            fill="var(--series-2)"
            stroke="var(--surface)"
            strokeWidth={2}
            maxBarSize={24}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** The same numbers as the charts, for screen readers and anyone who prefers a table. */
export function SeriesTable({ points }: { points: DayPoint[] }) {
  return (
    <details className="mt-3 text-xs">
      <summary className="cursor-pointer text-muted hover:text-text">View as table</summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-border">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-surface-2 text-muted">
            <tr>
              <th scope="col" className="px-3 py-1.5 font-medium">
                Date
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                Incidents
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                High
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                First response
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                MTTA
              </th>
              <th scope="col" className="px-3 py-1.5 text-right font-medium">
                MTTR
              </th>
            </tr>
          </thead>
          <tbody className="tabular divide-y divide-border">
            {points.map((p) => (
              <tr key={p.date}>
                <td className="px-3 py-1.5">{shortDate(p.date)}</td>
                <td className="px-3 py-1.5 text-right">{p.incidents}</td>
                <td className="px-3 py-1.5 text-right">{p.high}</td>
                <td className="px-3 py-1.5 text-right">
                  {formatDuration(p.time_to_first_response_seconds)}
                </td>
                <td className="px-3 py-1.5 text-right">{formatDuration(p.mtta_seconds)}</td>
                <td className="px-3 py-1.5 text-right">{formatDuration(p.mttr_seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
