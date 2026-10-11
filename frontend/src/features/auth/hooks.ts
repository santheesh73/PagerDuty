import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { keys } from "@/api/keys";
import type { LoginResult, Me, MfaStatus } from "@/api/types";

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

export function isMfaChallenge(result: LoginResult): result is { mfa_required: true } {
  return "mfa_required" in result && result.mfa_required === true;
}

function signedIn(client: ReturnType<typeof useQueryClient>, me: Me) {
  client.clear();
  client.setQueryData(keys.me, me);
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<LoginResult>("/auth/login/", { method: "POST", body }),
    onSuccess: (result) => {
      if (!isMfaChallenge(result)) signedIn(client, result);
    },
  });
}

/** The second sign-in step: a code from an authenticator app, or a backup code. */
export function useLoginMfa() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => api<Me>("/auth/mfa/", { method: "POST", body: { code } }),
    onSuccess: (me) => signedIn(client, me),
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

export function useMfaStatus(enabled = true) {
  return useQuery({
    queryKey: ["me", "mfa"],
    queryFn: () => api<MfaStatus>("/me/mfa/"),
    enabled,
    staleTime: 30_000,
  });
}

export function usePasswordResetRequest() {
  return useMutation({
    mutationFn: (email: string) =>
      api<void>("/auth/password-reset/", { method: "POST", body: { email } }),
  });
}

export function usePasswordResetConfirm() {
  return useMutation({
    mutationFn: (body: { uid: string; token: string; new_password: string }) =>
      api<void>("/auth/password-reset/confirm/", { method: "POST", body }),
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
