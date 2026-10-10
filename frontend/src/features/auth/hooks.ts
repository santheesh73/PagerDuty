import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { keys } from "@/api/keys";
import type { Me } from "@/api/types";

/** The signed-in user, or null when signed out (a 403 here is "not logged in", not an error). */
export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api<Me>("/me/");
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403))
          return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<Me>("/auth/login/", { method: "POST", body }),
    onSuccess: (me) => {
      client.clear();
      client.setQueryData(keys.me, me);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/auth/logout/", { method: "POST" }),
    onSettled: () => {
      client.clear();
      client.setQueryData(keys.me, null);
    },
  });
}

export type Role = "admin" | "responder" | "viewer";
const RANK: Record<Role, number> = { viewer: 0, responder: 1, admin: 2 };

/** Mirror of the backend's permission model, used only to hide controls you can't use. */
export function hasRole(
  me: Me | null | undefined,
  teamId: number | undefined,
  minimum: Role,
): boolean {
  if (!me || teamId === undefined) return false;
  if (me.is_staff) return true;
  const membership = me.memberships.find((m) => m.team.id === teamId);
  return membership ? RANK[membership.role as Role] >= RANK[minimum] : false;
}

export function adminTeams(me: Me | null | undefined) {
  if (!me) return [];
  return me.memberships.filter((m) => me.is_staff || m.role === "admin").map((m) => m.team);
}
