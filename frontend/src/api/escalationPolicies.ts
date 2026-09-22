import { apiClient } from './client';
import {
  CreateEscalationLevelInput,
  CreateEscalationPolicyInput,
  EscalationLevel,
  EscalationPolicy,
  UpdateEscalationLevelInput,
  UpdateEscalationPolicyInput,
} from '../types/escalation';

export interface EscalationPolicyFilters {
  team?: number;
  is_active?: boolean;
}

export const getEscalationPolicies = async (
  filters?: EscalationPolicyFilters
): Promise<EscalationPolicy[]> => {
  return apiClient.get<EscalationPolicy[]>('/escalation-policies/', {
    params: filters as Record<string, string | number | boolean>,
  });
};

export const getEscalationPolicy = async (id: number): Promise<EscalationPolicy> => {
  return apiClient.get<EscalationPolicy>(`/escalation-policies/${id}/`);
};

export const createEscalationPolicy = async (
  data: CreateEscalationPolicyInput
): Promise<EscalationPolicy> => {
  return apiClient.post<EscalationPolicy>('/escalation-policies/', data);
};

export const updateEscalationPolicy = async (
  id: number,
  data: UpdateEscalationPolicyInput
): Promise<EscalationPolicy> => {
  return apiClient.patch<EscalationPolicy>(`/escalation-policies/${id}/`, data);
};

export const getEscalationLevels = async (policyId?: number): Promise<EscalationLevel[]> => {
  return apiClient.get<EscalationLevel[]>('/escalation-levels/', {
    params: policyId ? { policy: policyId } : undefined,
  });
};

export const createEscalationLevel = async (
  data: CreateEscalationLevelInput
): Promise<EscalationLevel> => {
  return apiClient.post<EscalationLevel>('/escalation-levels/', data);
};

export const updateEscalationLevel = async (
  id: number,
  data: UpdateEscalationLevelInput
): Promise<EscalationLevel> => {
  return apiClient.patch<EscalationLevel>(`/escalation-levels/${id}/`, data);
};

export const deleteEscalationLevel = async (id: number): Promise<void> => {
  return apiClient.delete<void>(`/escalation-levels/${id}/`);
};

export const reorderEscalationLevels = async (
  policyId: number,
  levelIds: number[]
): Promise<EscalationPolicy> => {
  return apiClient.post<EscalationPolicy>(`/escalation-policies/${policyId}/reorder-levels/`, {
    level_ids: levelIds,
  });
};

