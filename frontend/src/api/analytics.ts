import { apiClient } from './client';
import {
  AnalyticsRange,
  AnalyticsSummary,
  IncidentTrendPoint,
  ServiceIncidentCount,
  SeverityCount,
} from '../types/analytics';

export const getAnalyticsSummary = async (range?: AnalyticsRange | string): Promise<AnalyticsSummary> => {
  return apiClient.get<AnalyticsSummary>('/analytics/summary/', {
    params: range ? { range } : undefined,
  });
};

export const getIncidentsByService = async (
  range?: AnalyticsRange | string
): Promise<ServiceIncidentCount[]> => {
  return apiClient.get<ServiceIncidentCount[]>('/analytics/incidents-by-service/', {
    params: range ? { range } : undefined,
  });
};

export const getSeverityDistribution = async (
  range?: AnalyticsRange | string
): Promise<SeverityCount[]> => {
  return apiClient.get<SeverityCount[]>('/analytics/severity-distribution/', {
    params: range ? { range } : undefined,
  });
};

export const getIncidentTrend = async (
  range?: AnalyticsRange | string
): Promise<IncidentTrendPoint[]> => {
  return apiClient.get<IncidentTrendPoint[]>('/analytics/trend/', {
    params: range ? { range } : undefined,
  });
};
