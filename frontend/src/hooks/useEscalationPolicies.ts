import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CreateEscalationLevelInput,
  CreateEscalationPolicyInput,
  EscalationLevel,
  EscalationPolicy,
  UpdateEscalationLevelInput,
  UpdateEscalationPolicyInput,
} from '../types/escalation';
import {
  EscalationPolicyFilters,
  createEscalationLevel,
  createEscalationPolicy,
  deleteEscalationLevel,
  getEscalationLevels,
  getEscalationPolicies,
  getEscalationPolicy,
  reorderEscalationLevels,
  updateEscalationLevel,
  updateEscalationPolicy,
} from '../api/escalationPolicies';
import { queryKeys } from '../app/queryClient';

export function useEscalationPolicies(filters?: EscalationPolicyFilters) {
  return useQuery<EscalationPolicy[]>({
    queryKey: queryKeys.escalationPolicies(filters as Record<string, unknown>),
    queryFn: () => getEscalationPolicies(filters),
    staleTime: 30_000,
  });
}

export function useEscalationPolicy(id?: number | string) {
  const numericId = id ? Number(id) : undefined;
  return useQuery<EscalationPolicy>({
    queryKey: queryKeys.escalationPolicy(numericId ?? 0),
    queryFn: () => getEscalationPolicy(numericId!),
    enabled: Boolean(numericId),
  });
}

export function useEscalationLevels(policyId?: number | string) {
  const numericId = policyId ? Number(policyId) : undefined;
  return useQuery<EscalationLevel[]>({
    queryKey: queryKeys.escalationLevels(numericId),
    queryFn: () => getEscalationLevels(numericId),
    enabled: Boolean(numericId),
    staleTime: 15_000,
  });
}

export function useCreateEscalationPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateEscalationPolicyInput) => createEscalationPolicy(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['escalation-policies'] });
    },
  });
}

export function useUpdateEscalationPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateEscalationPolicyInput }) =>
      updateEscalationPolicy(id, data),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['escalation-policies'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationPolicy(id) });
    },
  });
}

export function useCreateEscalationLevel(policyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateEscalationLevelInput) => createEscalationLevel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationPolicy(policyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationLevels(policyId) });
      queryClient.invalidateQueries({ queryKey: ['escalation-policies'] });
    },
  });
}

export function useUpdateEscalationLevel(policyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateEscalationLevelInput }) =>
      updateEscalationLevel(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationPolicy(policyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationLevels(policyId) });
      queryClient.invalidateQueries({ queryKey: ['escalation-policies'] });
    },
  });
}

export function useDeleteEscalationLevel(policyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteEscalationLevel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationPolicy(policyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationLevels(policyId) });
      queryClient.invalidateQueries({ queryKey: ['escalation-policies'] });
    },
  });
}

export function useReorderEscalationLevels(policyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (levelIds: number[]) => reorderEscalationLevels(policyId, levelIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationPolicy(policyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.escalationLevels(policyId) });
      queryClient.invalidateQueries({ queryKey: ['escalation-policies'] });
    },
  });
}
