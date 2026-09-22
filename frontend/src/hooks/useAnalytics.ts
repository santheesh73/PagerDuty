import { useQuery } from '@tanstack/react-query';
import {
  AnalyticsRange,
  AnalyticsSummary,
  IncidentTrendPoint,
  ServiceIncidentCount,
  SeverityCount,
} from '../types/analytics';
import {
  getAnalyticsSummary,
  getIncidentTrend,
  getIncidentsByService,
  getSeverityDistribution,
} from '../api/analytics';
import { queryKeys } from '../app/queryClient';

export function useAnalyticsSummary(range?: AnalyticsRange | string) {
  return useQuery<AnalyticsSummary>({
    queryKey: queryKeys.analytics.summary(range),
    queryFn: () => getAnalyticsSummary(range),
    staleTime: 60_000,
  });
}

export function useIncidentsByService(range?: AnalyticsRange | string) {
  return useQuery<ServiceIncidentCount[]>({
    queryKey: queryKeys.analytics.byService(range),
    queryFn: () => getIncidentsByService(range),
    staleTime: 60_000,
  });
}

export function useSeverityDistribution(range?: AnalyticsRange | string) {
  return useQuery<SeverityCount[]>({
    queryKey: queryKeys.analytics.severity(range),
    queryFn: () => getSeverityDistribution(range),
    staleTime: 60_000,
  });
}

export function useIncidentTrend(range?: AnalyticsRange | string) {
  return useQuery<IncidentTrendPoint[]>({
    queryKey: queryKeys.analytics.trend(range),
    queryFn: () => getIncidentTrend(range),
    staleTime: 60_000,
  });
}
