import type { EscalationPolicy, EscalationPolicyInput } from "@/api/types";

export interface DraftTarget {
  type: "user" | "schedule";
  id: number;
  name: string;
}
export interface DraftLevel {
  key: number;
  delay_minutes: number;
  targets: DraftTarget[];
}
export interface Draft {
  name: string;
  team: number;
  num_loops: number;
  levels: DraftLevel[];
}

let nextKey = 1;
export const newLevel = (delay = 5): DraftLevel => ({
  key: nextKey++,
  delay_minutes: delay,
  targets: [],
});

export function draftFrom(policy: EscalationPolicy | undefined, team: number): Draft {
  if (!policy) return { name: "", team, num_loops: 0, levels: [newLevel()] };
  return {
    name: policy.name,
    team: policy.team,
    num_loops: policy.num_loops,
    levels: policy.rules.map((rule) => ({
      key: nextKey++,
      delay_minutes: rule.delay_minutes,
      targets: rule.targets.map((t) => ({ type: t.type, id: t.id, name: t.name })),
    })),
  };
}

export function toPayload(draft: Draft): EscalationPolicyInput {
  return {
    name: draft.name.trim(),
    team: draft.team,
    num_loops: draft.num_loops,
    rules: draft.levels.map((level) => ({
      delay_minutes: level.delay_minutes,
      targets: level.targets.map(({ type, id }) => ({ type, id })),
    })),
  };
}

export function validate(draft: Draft): string | null {
  if (!draft.name.trim()) return "Give the policy a name.";
  if (draft.levels.length === 0) return "Add at least one level.";
  const empty = draft.levels.findIndex((l) => l.targets.length === 0);
  if (empty >= 0) return `Level ${empty + 1} needs someone to page.`;
  if (draft.levels.some((l) => !(l.delay_minutes >= 1)))
    return "Every delay must be at least 1 minute.";
  return null;
}
