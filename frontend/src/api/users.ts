import { apiClient } from './client';
import { Team, TeamMembership, User } from '../types/user';

export interface UserFilters {
  team?: number;
}

export interface TeamFilters {
  is_active?: boolean;
}

export interface TeamMemberFilters {
  is_active?: boolean;
}

export const getUsers = async (filters?: UserFilters): Promise<User[]> => {
  return apiClient.get<User[]>('/users/', {
    params: filters as Record<string, string | number | boolean>,
  });
};

export const getTeams = async (filters?: TeamFilters): Promise<Team[]> => {
  return apiClient.get<Team[]>('/teams/', {
    params: filters as Record<string, string | number | boolean>,
  });
};

export const getTeam = async (id: number): Promise<Team> => {
  return apiClient.get<Team>(`/teams/${id}/`);
};

export const getTeamMembers = async (
  teamId: number,
  filters?: TeamMemberFilters
): Promise<TeamMembership[]> => {
  return apiClient.get<TeamMembership[]>(`/teams/${teamId}/members/`, {
    params: filters as Record<string, string | number | boolean>,
  });
};
