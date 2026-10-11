import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AuditEvent, BackupCodes, MfaSetup, Page, SessionInfo } from "@/api/types";

const MFA = ["me", "mfa"];
const SESSIONS = ["me", "sessions"];

export function useMfaSetup() {
  return useMutation({ mutationFn: () => api<MfaSetup>("/me/mfa/setup/", { method: "POST" }) });
}

export function useMfaConfirm() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      api<BackupCodes>("/me/mfa/confirm/", { method: "POST", body: { code } }),
    onSuccess: () => void client.invalidateQueries({ queryKey: MFA }),
  });
}

export function useMfaDisable() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { password: string; code: string }) =>
      api<void>("/me/mfa/disable/", { method: "POST", body }),
    onSuccess: () => void client.invalidateQueries({ queryKey: MFA }),
  });
}

export function useRegenerateBackupCodes() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      api<BackupCodes>("/me/mfa/backup-codes/", { method: "POST", body: { code } }),
    onSuccess: () => void client.invalidateQueries({ queryKey: MFA }),
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api<void>("/me/password/", { method: "POST", body }),
    onSuccess: () => void client.invalidateQueries({ queryKey: SESSIONS }),
  });
}

export function useSessions() {
  return useQuery({ queryKey: SESSIONS, queryFn: () => api<SessionInfo[]>("/me/sessions/") });
}

export function useRevokeSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/me/sessions/${id}/`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: SESSIONS }),
  });
}

export function useRevokeOtherSessions() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ count: number }>("/me/sessions/revoke-others/", { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: SESSIONS }),
  });
}

export function useAuditEvents(action: string) {
  return useQuery({
    queryKey: ["audit-events", action],
    queryFn: () => api<Page<AuditEvent>>("/audit-events/", { query: { action, page_size: 100 } }),
  });
}
