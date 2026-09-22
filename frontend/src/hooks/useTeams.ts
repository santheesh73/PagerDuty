import { useQuery } from '@tanstack/react-query';
import { TeamFilters, TeamMemberFilters, UserFilters, getTeamMembers, getTeams, getUsers } from '../api/users';
import { queryKeys } from '../app/queryClient';
import { Team, TeamMembership, User } from '../types/user';

export function useTeams(filters?: TeamFilters) {
  return useQuery<Team[]>({
    queryKey: queryKeys.teams(filters as Record<string, unknown>),
    queryFn: () => getTeams(filters),
    staleTime: 60_000,
  });
}

export function useTeamMembers(teamId?: number, filters?: TeamMemberFilters) {
  return useQuery<TeamMembership[]>({
    queryKey: queryKeys.teamMembers(teamId ?? 0),
    queryFn: () => getTeamMembers(teamId!, filters),
    enabled: Boolean(teamId),
    staleTime: 60_000,
  });
}

export function useUsers(filters?: UserFilters) {
  return useQuery<User[]>({
    queryKey: queryKeys.users(filters as Record<string, unknown>),
    queryFn: () => getUsers(filters),
    staleTime: 60_000,
  });
}
