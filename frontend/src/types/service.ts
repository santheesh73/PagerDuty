import { TeamSummary } from './user';

export type ServiceStatus = 'HEALTHY' | 'DEGRADED' | 'DOWN' | 'MAINTENANCE';

export interface ServiceSummary {
  id: number;
  name: string;
  slug: string;
  status: ServiceStatus;
}

export interface Service extends ServiceSummary {
  description: string;
  team: TeamSummary;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
