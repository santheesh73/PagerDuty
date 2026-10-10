/** Query keys in one place so mutations invalidate exactly what they changed. */
export const keys = {
  me: ["me"] as const,
  teams: ["teams"] as const,
  teamMembers: (teamId: number) => ["teams", teamId, "members"] as const,
  users: (teamId?: number) => ["users", teamId ?? "all"] as const,
  incidents: {
    all: ["incidents"] as const,
    list: (filters: Record<string, unknown>) => ["incidents", "list", filters] as const,
    detail: (id: number) => ["incidents", "detail", id] as const,
    timeline: (id: number) => ["incidents", "timeline", id] as const,
    alerts: (id: number) => ["incidents", "alerts", id] as const,
  },
  services: {
    all: ["services"] as const,
    detail: (id: number) => ["services", id] as const,
  },
  policies: {
    all: ["policies"] as const,
    detail: (id: number) => ["policies", id] as const,
  },
  schedules: {
    all: ["schedules"] as const,
    detail: (id: number) => ["schedules", id] as const,
    shifts: (id: number, since: string, until: string) =>
      ["schedules", id, "shifts", since, until] as const,
    overrides: (id: number) => ["schedules", id, "overrides"] as const,
    oncall: (id: number) => ["schedules", id, "oncall"] as const,
  },
  oncalls: ["oncalls"] as const,
  notifications: {
    all: ["notifications"] as const,
    list: (unread: boolean) => ["notifications", "list", unread] as const,
    unread: ["notifications", "unread-count"] as const,
  },
  analytics: {
    summary: (params: Record<string, unknown>) => ["analytics", "summary", params] as const,
    series: (params: Record<string, unknown>) => ["analytics", "series", params] as const,
  },
};
