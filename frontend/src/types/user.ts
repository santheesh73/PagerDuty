/**
 * Identity and team models mirroring DRF serializers.
 */

export interface UserSummary {
  id: number;
  username: string;
  name: string;
  email: string;
}

export interface User extends UserSummary {
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  date_joined: string;
}

export interface TeamSummary {
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
}

export interface Team extends TeamSummary {
  description: string;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export type TeamMembershipRole = 'ENGINEER' | 'LEAD' | 'RESPONDER';

export interface TeamMembership {
  id: number;
  user: UserSummary;
  team: TeamSummary;
  role: TeamMembershipRole;
  is_active: boolean;
  joined_at: string;
  created_at: string;
  updated_at: string;
}
