import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { keys } from "@/api/keys";
import type { EscalationPolicy, EscalationPolicyInput, OnCallPolicy, Page } from "@/api/types";

export const MAX_LEVELS = 10;
export const MAX_TARGETS = 5;

export function usePolicies() {
  return useQuery({
    queryKey: keys.policies.all,
    queryFn: () =>
      api<Page<EscalationPolicy>>("/escalation-policies/", { query: { page_size: 100 } }),
    select: (page) => page.results,
  });
}

export function usePolicy(id: number | undefined) {
  return useQuery({
    queryKey: keys.policies.detail(id ?? 0),
    queryFn: () => api<EscalationPolicy>(`/escalation-policies/${id}/`),
    enabled: id !== undefined,
  });
}

export function useSavePolicy(id?: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: EscalationPolicyInput) =>
      id
        ? api<EscalationPolicy>(`/escalation-policies/${id}/`, { method: "PUT", body })
        : api<EscalationPolicy>("/escalation-policies/", { method: "POST", body }),
    onSuccess: (policy) => {
      client.setQueryData(keys.policies.detail(policy.id), policy);
      void client.invalidateQueries({ queryKey: keys.policies.all });
      void client.invalidateQueries({ queryKey: keys.oncalls });
      toast.success(id ? "Policy saved" : `Created ${policy.name}`, {
        description: id ? "Open incidents keep the version they started with." : undefined,
      });
    },
  });
}

export function useDeletePolicy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/escalation-policies/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.policies.all });
      toast.success("Policy deleted");
    },
    onError: (error) =>
      toast.error("Couldn't delete the policy", {
        description: error instanceof ApiError ? error.message : undefined,
      }),
  });
}

export function useOnCalls() {
  return useQuery({
    queryKey: keys.oncalls,
    queryFn: () => api<OnCallPolicy[]>("/oncalls/"),
    refetchInterval: 60_000,
  });
}
