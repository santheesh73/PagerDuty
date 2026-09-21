export type EscalationTargetType = 'CURRENT_ON_CALL' | 'USER';

export interface EscalationLevel {
  id: number;
  policy: number;
  order: number;
  target_type: EscalationTargetType;
  target_user: number | null;
  target_username: string | null;
  wait_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface EscalationPolicy {
  id: number;
  name: string;
  slug: string;
  team: number;
  team_name: string;
  is_active: boolean;
  levels: EscalationLevel[];
  created_at: string;
  updated_at: string;
}
