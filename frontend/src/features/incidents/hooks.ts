import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { keys } from "@/api/keys";
import type {
  Alert,
  CursorPage,
  Incident,
  IncidentAction,
  IncidentDetail,
  IncidentEvent,
  IncidentStatus,
} from "@/api/types";

export const POLL_MS = 10_000;

export interface IncidentFilters {
  status?: string;
  urgency?: string;
  service?: string;
  team?: string;
  assignee?: string;
  search?: string;
  since?: string;
}

export function useIncidents(filters: IncidentFilters, { pageSize = 25, poll = true } = {}) {
  return useInfiniteQuery({
    queryKey: keys.incidents.list({ ...filters, pageSize }),
    queryFn: ({ pageParam, signal }) =>
      pageParam
        ? api<CursorPage<Incident>>(pageParam, { signal })
        : api<CursorPage<Incident>>("/incidents/", {
            query: { ...filters, page_size: pageSize },
            signal,
          }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
    refetchInterval: poll ? POLL_MS : false,
  });
}

export function useIncident(id: number) {
  return useQuery({
    queryKey: keys.incidents.detail(id),
    queryFn: ({ signal }) => api<IncidentDetail>(`/incidents/${id}/`, { signal }),
    refetchInterval: POLL_MS,
  });
}

export function useTimeline(id: number) {
  return useQuery({
    queryKey: keys.incidents.timeline(id),
    queryFn: ({ signal }) =>
      api<CursorPage<IncidentEvent>>(`/incidents/${id}/timeline/`, { signal }),
    refetchInterval: POLL_MS,
  });
}

export function useAlerts(id: number, enabled = true) {
  return useQuery({
    queryKey: keys.incidents.alerts(id),
    queryFn: ({ signal }) => api<CursorPage<Alert>>(`/incidents/${id}/alerts/`, { signal }),
    enabled,
  });
}

/** Mirror of the backend transition table: which actions each status allows. */
export const ALLOWED: Record<IncidentStatus, IncidentAction[]> = {
  triggered: ["acknowledge", "resolve", "reassign", "escalate", "add_note"],
  acknowledged: ["unacknowledge", "resolve", "reassign", "escalate", "add_note"],
  resolved: [],
};

type SimpleAction = "acknowledge" | "unacknowledge" | "resolve" | "escalate";

/** Status we can predict without asking the server. Escalate isn't optimistic: the next
 *  responder comes from the on-call schedule, which only the backend can resolve. */
const OPTIMISTIC: Partial<Record<SimpleAction, IncidentStatus>> = {
  acknowledge: "acknowledged",
  unacknowledge: "triggered",
  resolve: "resolved",
};

const PAST: Record<SimpleAction, string> = {
  acknowledge: "Acknowledged",
  unacknowledge: "Unacknowledged",
  resolve: "Resolved",
  escalate: "Escalated",
};

export function useIncidentAction(id: number) {
  const client = useQueryClient();
  const detailKey = keys.incidents.detail(id);

  return useMutation({
    mutationFn: (action: SimpleAction) =>
      api<IncidentDetail>(`/incidents/${id}/${action}/`, { method: "POST" }),
    onMutate: async (action) => {
      const status = OPTIMISTIC[action];
      if (!status) return { previous: undefined };
      await client.cancelQueries({ queryKey: detailKey });
      const previous = client.getQueryData<IncidentDetail>(detailKey);
      if (previous) {
        client.setQueryData<IncidentDetail>(detailKey, {
          ...previous,
          status,
          allowed_actions: previous.allowed_actions.length ? ALLOWED[status] : [],
          next_escalation_at: status === "triggered" ? previous.next_escalation_at : null,
        });
      }
      return { previous };
    },
    onError: (error, action, context) => {
      if (context?.previous) client.setQueryData(detailKey, context.previous);
      toast.error(`Couldn't ${action} the incident`, {
        description: error instanceof ApiError ? error.message : undefined,
      });
    },
    onSuccess: (incident, action) => {
      client.setQueryData(detailKey, incident);
      toast.success(`${PAST[action]} #${incident.number}`);
    },
    onSettled: () => invalidateIncident(client, id),
  });
}

export function useReassign(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (assignee: number) =>
      api<IncidentDetail>(`/incidents/${id}/reassign/`, { method: "POST", body: { assignee } }),
    onSuccess: (incident) => {
      client.setQueryData(keys.incidents.detail(id), incident);
      toast.success(`Reassigned to ${incident.assignee?.name ?? "nobody"}`);
    },
    onError: (error) =>
      toast.error("Couldn't reassign", {
        description: error instanceof ApiError ? error.message : undefined,
      }),
    onSettled: () => invalidateIncident(client, id),
  });
}

export function useAddNote(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (text: string) =>
      api<IncidentEvent>(`/incidents/${id}/notes/`, { method: "POST", body: { text } }),
    onSuccess: (event) => {
      // Prepend so the note shows instantly; the poll reconciles ordering.
      client.setQueryData<CursorPage<IncidentEvent>>(keys.incidents.timeline(id), (page) =>
        page ? { ...page, results: [event, ...page.results] } : page,
      );
      toast.success("Note added");
    },
    onError: (error) =>
      toast.error("Couldn't add the note", {
        description: error instanceof ApiError ? error.message : undefined,
      }),
    onSettled: () => client.invalidateQueries({ queryKey: keys.incidents.timeline(id) }),
  });
}

function invalidateIncident(client: ReturnType<typeof useQueryClient>, id: number) {
  void client.invalidateQueries({ queryKey: keys.incidents.detail(id) });
  void client.invalidateQueries({ queryKey: keys.incidents.timeline(id) });
  void client.invalidateQueries({ queryKey: ["incidents", "list"] });
  void client.invalidateQueries({ queryKey: keys.services.all });
}

export function flattenPages<T>(data: InfiniteData<CursorPage<T>> | undefined): T[] {
  return data?.pages.flatMap((page) => page.results) ?? [];
}
