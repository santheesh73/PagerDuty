import type { components } from "./schema";

type S = components["schemas"];

export type Me = S["Me"];
export type UserSummary = S["UserSummary"];
export type Team = S["Team"];
export type TeamMember = S["TeamMember"];
export type Incident = S["Incident"];
export type IncidentDetail = S["IncidentDetail"];
export type IncidentEvent = S["IncidentEvent"];
export type Alert = S["Alert"];
export type Service = S["Service"];
export type ServiceInput = S["ServiceRequest"];
export type ServiceMode = S["ServiceModeEnum"];
export type TestAlertResult = S["TestAlertResult"];
export type EscalationPolicy = S["EscalationPolicy"];
export type EscalationPolicyInput = S["EscalationPolicyRequest"];
export type Rule = S["Rule"];
export type Target = S["Target"];
export type Schedule = S["Schedule"];
export type ScheduleInput = S["ScheduleRequest"];
export type Layer = S["Layer"];
export type LayerInput = S["LayerRequest"];
export type Override = S["Override"];
export type Shift = S["Shift"];
export type OnCallNow = S["OnCallNow"];
export type OnCallPolicy = S["OnCallPolicy"];
export type Notification = S["Notification"];
export type AnalyticsSummary = S["Summary"];
export type DayPoint = S["DayPoint"];

export type IncidentStatus = S["IncidentStatusEnum"];
export type Urgency = "high" | "low";
export type IncidentAction =
  "acknowledge" | "unacknowledge" | "resolve" | "reassign" | "escalate" | "add_note";

export interface CursorPage<T> {
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** The escalation snapshot as served on incident detail (names added for display). */
export interface SnapshotTarget {
  type: "user" | "schedule";
  id: number;
  name?: string;
}
export interface SnapshotRule {
  level: number;
  delay_minutes: number;
  targets: SnapshotTarget[];
}
export interface EscalationSnapshot {
  v: number;
  policy_id: number | null;
  policy_name: string;
  num_loops: number;
  rules: SnapshotRule[];
}
