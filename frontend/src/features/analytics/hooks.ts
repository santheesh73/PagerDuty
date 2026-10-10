import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { keys } from "@/api/keys";
import type { AnalyticsSummary, DayPoint } from "@/api/types";

export interface AnalyticsParams {
  days: number;
  service?: string;
}

/** Whole local days ending today, so day buckets line up with the chart's x-axis. */
export function windowFor(days: number): { since: string; until: string } {
  const end = new Date();
  end.setHours(24, 0, 0, 0);
  const start = new Date(end.getTime() - days * 86_400_000);
  return { since: start.toISOString(), until: end.toISOString() };
}

const tz = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export function useAnalyticsSummary(params: AnalyticsParams) {
  return useQuery({
    queryKey: keys.analytics.summary({ ...params }),
    queryFn: () =>
      api<AnalyticsSummary>("/analytics/summary/", {
        query: { ...windowFor(params.days), service: params.service },
      }),
    placeholderData: (previous) => previous,
    refetchInterval: 60_000,
  });
}

export function useAnalyticsSeries(params: AnalyticsParams) {
  return useQuery({
    queryKey: keys.analytics.series({ ...params }),
    queryFn: () =>
      api<DayPoint[]>("/analytics/timeseries/", {
        query: { ...windowFor(params.days), service: params.service, tz: tz() },
      }),
    placeholderData: (previous) => previous,
  });
}
