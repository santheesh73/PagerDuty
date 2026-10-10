import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { keys } from "@/api/keys";
import type { Notification, Page } from "@/api/types";

export function useUnreadCount() {
  return useQuery({
    queryKey: keys.notifications.unread,
    queryFn: () => api<{ count: number }>("/notifications/unread-count/"),
    refetchInterval: 15_000,
  });
}

export function useNotifications(unread: boolean) {
  return useQuery({
    queryKey: keys.notifications.list(unread),
    queryFn: () =>
      api<Page<Notification>>("/notifications/", {
        query: { unread: unread ? 1 : undefined, page_size: 50 },
      }),
    refetchInterval: 15_000,
  });
}

export function useMarkRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<Notification>(`/notifications/${id}/read/`, { method: "POST" }),
    onSettled: () => client.invalidateQueries({ queryKey: keys.notifications.all }),
  });
}

export function useMarkAllRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ count: number }>("/notifications/read-all/", { method: "POST" }),
    onSettled: () => client.invalidateQueries({ queryKey: keys.notifications.all }),
  });
}
