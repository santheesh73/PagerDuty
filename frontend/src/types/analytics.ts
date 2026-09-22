export interface AnalyticsSummary {
  range_days: number;
  incident_count: number;
  active_incidents: number;
  critical_incidents: number;
  mtta_seconds: number | null;
  mttr_seconds: number | null;
}

export interface ServiceIncidentCount {
  service_id: number;
  service_name: string;
  count: number;
}

export interface SeverityCount {
  severity: string;
  count: number;
}

export interface IncidentTrendPoint {
  date: string;
  count: number;
}

export type AnalyticsRange = '7d' | '30d' | '90d';

