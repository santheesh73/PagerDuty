import { ServiceSummary } from './service';
import { UserSummary } from './user';

export type IncidentStatus = 'triggered' | 'acknowledged' | 'resolved';

export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface IncidentSummary {
  id: number;
  title: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  triggered_at: string;
}

export interface Incident {
  id: number;
  title: string;
  service: ServiceSummary;
  severity: IncidentSeverity;
  status: IncidentStatus;
  assigned_user: UserSummary | null;
  fingerprint: string;
  triggered_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  alert_count: number;
  created_at: string;
  updated_at: string;
}

export type IncidentEventType =
  | 'INCIDENT_CREATED'
  | 'INCIDENT_ACKNOWLEDGED'
  | 'INCIDENT_RESOLVED'
  | 'INCIDENT_REOPENED'
  | 'RESPONDER_ASSIGNED'
  | 'ALERT_ATTACHED'
  | 'ROUTING_UNAVAILABLE'
  | 'ESCALATION_STARTED'
  | 'INCIDENT_ESCALATED'
  | 'ESCALATION_EXHAUSTED'
  | 'ESCALATION_TARGET_UNAVAILABLE'
  | string;

export interface IncidentEvent {
  id: number;
  incident_id: number;
  event_type: IncidentEventType;
  actor: UserSummary | null;
  metadata: Record<string, unknown>;
  created_at: string;
}
