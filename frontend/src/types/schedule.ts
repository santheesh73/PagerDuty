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

export interface OnCallUserSummary {
  id: number;
  username: string;
  name: string;
}

export interface OnCallResponse {
  schedule_id: number;
  at: string;
  user: OnCallUserSummary | null;
  source: 'OVERRIDE' | 'BASE' | string | null;
}

export interface CreateScheduleInput {
  name: string;
  slug: string;
  team_id: number;
  timezone: string;
  is_primary?: boolean;
  is_active?: boolean;
}

export interface UpdateScheduleInput {
  name?: string;
  slug?: string;
  team_id?: number;
  timezone?: string;
  is_primary?: boolean;
  is_active?: boolean;
}

export interface CreateRotationInput {
  schedule_id: number;
  user_id: number;
  start_time: string;
  end_time: string;
  is_override?: boolean;
}

export interface UpdateRotationInput {
  user_id?: number;
  start_time?: string;
  end_time?: string;
  is_override?: boolean;
}
