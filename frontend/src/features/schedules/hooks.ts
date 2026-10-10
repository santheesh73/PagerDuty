import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { keys } from "@/api/keys";
import type { OnCallNow, Override, Page, Schedule, ScheduleInput, Shift } from "@/api/types";

export const MAX_LAYERS = 5;
export const MAX_MEMBERS = 50;
export const TIME_ZONES: string[] =
  typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : ["UTC"];

const fail = (title: string) => (error: unknown) =>
  toast.error(title, { description: error instanceof ApiError ? error.message : undefined });

export function useSchedules() {
  return useQuery({
    queryKey: keys.schedules.all,
    queryFn: () => api<Page<Schedule>>("/schedules/", { query: { page_size: 100 } }),
    select: (page) => page.results,
  });
}

export function useSchedule(id: number) {
  return useQuery({
    queryKey: keys.schedules.detail(id),
    queryFn: () => api<Schedule>(`/schedules/${id}/`),
  });
}

export function useShifts(id: number, since: Date, until: Date) {
  const s = since.toISOString();
  const u = until.toISOString();
  return useQuery({
    queryKey: keys.schedules.shifts(id, s, u),
    queryFn: () => api<Shift[]>(`/schedules/${id}/shifts/`, { query: { since: s, until: u } }),
    placeholderData: (previous) => previous,
  });
}

export function useOnCallNow(id: number) {
  return useQuery({
    queryKey: keys.schedules.oncall(id),
    queryFn: () => api<OnCallNow>(`/schedules/${id}/oncall/`),
    refetchInterval: 60_000,
  });
}

export function useOverrides(id: number) {
  return useQuery({
    queryKey: keys.schedules.overrides(id),
    queryFn: () =>
      api<Override[]>(`/schedules/${id}/overrides/`, {
        query: { since: new Date(Date.now() - 86_400_000).toISOString() },
      }),
  });
}

function invalidateSchedule(client: ReturnType<typeof useQueryClient>, id: number) {
  void client.invalidateQueries({ queryKey: ["schedules", id] });
  void client.invalidateQueries({ queryKey: keys.schedules.all });
  void client.invalidateQueries({ queryKey: keys.oncalls });
}

export function useSaveSchedule(id?: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<ScheduleInput>) =>
      id
        ? api<Schedule>(`/schedules/${id}/`, { method: "PATCH", body })
        : api<Schedule>("/schedules/", { method: "POST", body }),
    onSuccess: (schedule) => {
      client.setQueryData(keys.schedules.detail(schedule.id), schedule);
      invalidateSchedule(client, schedule.id);
      toast.success(id ? "Schedule saved" : `Created ${schedule.name}`);
    },
  });
}

export function useCreateOverride(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { user: number; start: string; end: string }) =>
      api<Override>(`/schedules/${id}/overrides/`, { method: "POST", body }),
    onSuccess: () => {
      invalidateSchedule(client, id);
      toast.success("Override added");
    },
  });
}

export function useDeleteOverride(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (overrideId: number) =>
      api<void>(`/schedules/${id}/overrides/${overrideId}/`, { method: "DELETE" }),
    onSuccess: () => {
      invalidateSchedule(client, id);
      toast.success("Override removed");
    },
    onError: fail("Couldn't remove the override"),
  });
}
