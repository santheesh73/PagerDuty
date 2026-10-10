import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { keys } from "@/api/keys";
import type {
  Page,
  Service,
  ServiceInput,
  ServiceMode,
  TeamMember,
  TestAlertResult,
  UserSummary,
} from "@/api/types";

function errorToast(title: string) {
  return (error: unknown) =>
    toast.error(title, { description: error instanceof ApiError ? error.message : undefined });
}

export function useServices() {
  return useQuery({
    queryKey: keys.services.all,
    queryFn: () => api<Page<Service>>("/services/", { query: { page_size: 100 } }),
    select: (page) => page.results,
    refetchInterval: 30_000,
  });
}

export function useService(id: number) {
  return useQuery({
    queryKey: keys.services.detail(id),
    queryFn: () => api<Service>(`/services/${id}/`),
    refetchInterval: 15_000,
  });
}

export function useSaveService(id?: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<ServiceInput>) =>
      id
        ? api<Service>(`/services/${id}/`, { method: "PATCH", body })
        : api<Service>("/services/", { method: "POST", body }),
    onSuccess: (service) => {
      client.setQueryData(keys.services.detail(service.id), service);
      void client.invalidateQueries({ queryKey: keys.services.all });
      toast.success(id ? "Service saved" : `Created ${service.name}`);
    },
  });
}

export function useDeleteService() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/services/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.services.all });
      toast.success("Service deleted");
    },
    onError: errorToast("Couldn't delete the service"),
  });
}

export function useRotateKey(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<Service>(`/services/${id}/rotate-key/`, { method: "POST" }),
    onSuccess: (service) => {
      client.setQueryData(keys.services.detail(id), service);
      toast.success("Integration key rotated", {
        description: "The old key stops working immediately.",
      });
    },
    onError: errorToast("Couldn't rotate the key"),
  });
}

export function useSetMode(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { mode: ServiceMode; until?: string | null }) =>
      api<Service>(`/services/${id}/mode/`, { method: "POST", body }),
    onSuccess: (service) => {
      client.setQueryData(keys.services.detail(id), service);
      void client.invalidateQueries({ queryKey: keys.services.all });
      void client.invalidateQueries({ queryKey: keys.incidents.all });
      toast.success(`${service.name} is now in ${service.mode} mode`);
    },
    onError: errorToast("Couldn't change the mode"),
  });
}

export function useTestAlert(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<TestAlertResult>(`/services/${id}/test-alert/`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.incidents.all });
      void client.invalidateQueries({ queryKey: keys.services.all });
    },
    onError: errorToast("Couldn't send the test alert"),
  });
}

export function useTeamMembers(teamId: number | undefined) {
  return useQuery({
    queryKey: keys.teamMembers(teamId ?? 0),
    queryFn: () => api<TeamMember[]>(`/teams/${teamId}/members/`),
    enabled: teamId !== undefined,
    staleTime: 60_000,
  });
}

export function useUsers(teamId?: number) {
  return useQuery({
    queryKey: keys.users(teamId),
    queryFn: () => api<UserSummary[]>("/users/", { query: { team: teamId } }),
    staleTime: 60_000,
  });
}
