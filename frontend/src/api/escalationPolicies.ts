import { apiClient } from './client';
import { EscalationLevel, EscalationPolicy } from '../types/escalation';

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

export const getEscalationLevels = async (policyId?: number): Promise<EscalationLevel[]> => {
  return apiClient.get<EscalationLevel[]>('/escalation-levels/', {
    params: policyId ? { policy: policyId } : undefined,
  });
};
