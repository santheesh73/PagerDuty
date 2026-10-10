import type { IncidentDetail, Shift } from "@/api/types";

export function incidentFixture(overrides: Partial<IncidentDetail> = {}): IncidentDetail {
  return {
    id: 7,
    number: 1042,
    title: "Disk 95% full on db-1",
    status: "triggered",
    urgency: "high",
    service: { id: 3, name: "checkout-api", mode: "active", team: 1 },
    assignee: { id: 11, name: "Riley Chen", email: "riley@example.test", timezone: "UTC" },
    dedup_key: "db-1/disk",
    is_maintenance: false,
    escalation_level: 0,
    escalation_loop: 0,
    next_escalation_at: new Date(Date.now() + 5 * 60_000).toISOString(),
    triggered_at: new Date(Date.now() - 60_000).toISOString(),
    first_response_at: null,
    acknowledged_at: null,
    resolved_at: null,
    alert_count: 1,
    allowed_actions: ["acknowledge", "resolve", "reassign", "escalate", "add_note"],
    escalation_snapshot: {
      v: 1,
      policy_id: 1,
      policy_name: "Payments critical",
      num_loops: 0,
      rules: [
        {
          level: 0,
          delay_minutes: 5,
          targets: [{ type: "schedule", id: 2, name: "Payments primary" }],
        },
        { level: 1, delay_minutes: 10, targets: [{ type: "user", id: 12, name: "Ada Okafor" }] },
      ],
    },
    ...overrides,
  } as IncidentDetail;
}

export function shift(
  userId: number,
  name: string,
  start: string,
  end: string,
  source = "Primary",
): Shift {
  return {
    user: { id: userId, name, email: `${userId}@x.test`, timezone: "UTC" },
    start,
    end,
    source,
  };
}
