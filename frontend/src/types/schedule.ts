import { TeamSummary, UserSummary } from './user';

export interface ScheduleSummary {
  id: number;
  name: string;
  slug: string;
  timezone: string;
  is_primary: boolean;
  is_active: boolean;
}

export interface Schedule extends ScheduleSummary {
  team: TeamSummary;
  created_at: string;
  updated_at: string;
}

export interface ScheduleRotation {
  id: number;
  schedule: ScheduleSummary;
  user: UserSummary;
  start_time: string;
  end_time: string;
  is_override: boolean;
  created_at: string;
  updated_at: string;
}

export interface OnCallResponse {
  user: UserSummary | null;
  timestamp: string;
}
