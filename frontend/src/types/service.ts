import { TeamSummary } from './user';

export type ServiceStatus = 'HEALTHY' | 'DEGRADED' | 'DOWN' | 'MAINTENANCE';

export interface ServiceSummary {
  id: number;
  name: string;
  slug: string;
  status: ServiceStatus;
}

export interface ServicePolicySummary {
  id: number;
  name: string;
  slug: string;
}

export interface Service extends ServiceSummary {
  description: string;
  team: TeamSummary;
  escalation_policy?: ServicePolicySummary | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateServiceInput {
  name: string;
  slug: string;
  description?: string;
  team_id: number;
  status?: ServiceStatus;
  escalation_policy_id?: number | null;
  is_active?: boolean;
}

export interface UpdateServiceInput {
  name?: string;
  slug?: string;
  description?: string;
  team_id?: number;
  status?: ServiceStatus;
  escalation_policy_id?: number | null;
  is_active?: boolean;
}
