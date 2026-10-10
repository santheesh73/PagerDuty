import { useMemo } from "react";
import { ArrowDown, ArrowUp, Layers, Plus, Trash2, X } from "lucide-react";
import { ApiError } from "@/api/client";
import type { Schedule, TeamMember } from "@/api/types";
import { Avatar } from "@/components/Avatar";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Field, Input, Select } from "@/components/Field";
import { cn } from "@/lib/cn";
import { newLevel, type Draft, type DraftLevel, type DraftTarget } from "./draft";
import { MAX_LEVELS, MAX_TARGETS } from "./hooks";

/** Controlled editor for a policy's levels. Saving is the parent's job. */
export function PolicyEditor({
  draft,
  onChange,
  members,
  schedules,
  readOnly,
  error,
}: {
  draft: Draft;
  onChange: (draft: Draft) => void;
  members: TeamMember[];
  schedules: Schedule[];
  readOnly?: boolean;
  error?: ApiError | null;
}) {
  const update = (patch: Partial<Draft>) => onChange({ ...draft, ...patch });
  const setLevel = (index: number, patch: Partial<DraftLevel>) =>
    update({ levels: draft.levels.map((l, i) => (i === index ? { ...l, ...patch } : l)) });
  const move = (index: number, by: number) => {
    const levels = [...draft.levels];
    const [item] = levels.splice(index, 1);
    levels.splice(index + by, 0, item!);
    update({ levels });
  };
  const atLimit = draft.levels.length >= MAX_LEVELS;

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-[1fr_200px]">
        <Field label="Policy name" error={error?.fieldError("name")}>
          {(props) => (
            <Input
              {...props}
              value={draft.name}
              disabled={readOnly}
              onChange={(e) => update({ name: e.target.value })}
              placeholder="e.g. Payments critical"
            />
          )}
        </Field>
        <Field label="If nobody acknowledges" hint="Repeat the whole policy">
          {(props) => (
            <Select
              {...props}
              value={draft.num_loops}
              disabled={readOnly}
              onChange={(e) => update({ num_loops: Number(e.target.value) })}
            >
              <option value={0}>Stop after the last level</option>
              <option value={1}>Repeat once</option>
              <option value={2}>Repeat twice</option>
              <option value={3}>Repeat 3 times</option>
            </Select>
          )}
        </Field>
      </div>

      <ol className="space-y-3" aria-label="Escalation levels">
        {draft.levels.map((level, index) => (
          <li key={level.key}>
            <Card className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="inline-flex items-center gap-2 text-sm font-semibold">
                  <span className="grid size-6 place-items-center rounded-full bg-accent-soft text-xs text-accent">
                    {index + 1}
                  </span>
                  Level {index + 1}
                </span>
                {!readOnly && (
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Move level ${index + 1} up`}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                      icon={<ArrowUp className="size-3.5" />}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Move level ${index + 1} down`}
                      disabled={index === draft.levels.length - 1}
                      onClick={() => move(index, 1)}
                      icon={<ArrowDown className="size-3.5" />}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Remove level ${index + 1}`}
                      disabled={draft.levels.length === 1}
                      onClick={() => update({ levels: draft.levels.filter((_, i) => i !== index) })}
                      icon={<Trash2 className="size-3.5" />}
                    />
                  </div>
                )}
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {level.targets.map((target) => (
                  <span
                    key={`${target.type}-${target.id}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-2 py-0.5 pr-1 pl-0.5 text-sm"
                  >
                    {target.type === "user" ? (
                      <Avatar user={{ id: target.id, name: target.name }} size="sm" />
                    ) : (
                      <span className="grid size-6 place-items-center rounded-full bg-surface-3 text-muted">
                        <Layers className="size-3.5" aria-hidden />
                      </span>
                    )}
                    {target.name}
                    {target.type === "schedule" && (
                      <span className="text-xs text-subtle">(on-call)</span>
                    )}
                    {!readOnly && (
                      <button
                        type="button"
                        aria-label={`Remove ${target.name}`}
                        className="rounded-full p-0.5 text-subtle hover:bg-surface-3 hover:text-text"
                        onClick={() =>
                          setLevel(index, { targets: level.targets.filter((t) => t !== target) })
                        }
                      >
                        <X className="size-3.5" />
                      </button>
                    )}
                  </span>
                ))}
                {!readOnly && (
                  <TargetPicker
                    level={index + 1}
                    disabled={level.targets.length >= MAX_TARGETS}
                    members={members}
                    schedules={schedules}
                    taken={level.targets}
                    onPick={(t) => setLevel(index, { targets: [...level.targets, t] })}
                  />
                )}
              </div>
              {level.targets.length >= MAX_TARGETS && !readOnly && (
                <p className="mt-2 text-xs text-subtle">
                  Limit reached: {MAX_TARGETS} targets per level.
                </p>
              )}

              <div className="mt-4 flex items-center gap-2 border-t border-border pt-3 text-sm text-muted">
                <label htmlFor={`delay-${level.key}`}>
                  {index === draft.levels.length - 1
                    ? draft.num_loops > 0
                      ? "Repeat from level 1 after"
                      : "Stop escalating after"
                    : "Escalate to the next level after"}
                </label>
                <Input
                  id={`delay-${level.key}`}
                  type="number"
                  min={1}
                  max={1440}
                  className="h-8 w-20"
                  disabled={readOnly}
                  value={Number.isNaN(level.delay_minutes) ? "" : level.delay_minutes}
                  onChange={(e) => setLevel(index, { delay_minutes: e.target.valueAsNumber })}
                />
                minutes
              </div>
            </Card>
          </li>
        ))}
      </ol>

      {!readOnly && (
        <div className="flex items-center gap-3">
          <Button
            icon={<Plus className="size-4" />}
            disabled={atLimit}
            onClick={() =>
              update({
                levels: [...draft.levels, newLevel(draft.levels.at(-1)?.delay_minutes ?? 5)],
              })
            }
          >
            Add level
          </Button>
          <span className={cn("text-xs", atLimit ? "text-warning-fg" : "text-subtle")}>
            {draft.levels.length} / {MAX_LEVELS} levels
          </span>
        </div>
      )}
    </div>
  );
}

function TargetPicker({
  level,
  disabled,
  members,
  schedules,
  taken,
  onPick,
}: {
  level: number;
  disabled: boolean;
  members: TeamMember[];
  schedules: Schedule[];
  taken: DraftTarget[];
  onPick: (target: DraftTarget) => void;
}) {
  const isTaken = (type: string, id: number) => taken.some((t) => t.type === type && t.id === id);
  const people = useMemo(() => members.filter((m) => m.role !== "viewer"), [members]);
  return (
    <select
      aria-label={`Add someone to page at level ${level}`}
      disabled={disabled}
      value=""
      className="h-8 rounded-full border border-dashed border-border-strong bg-transparent px-3 text-sm text-muted hover:border-accent hover:text-accent disabled:opacity-50"
      onChange={(e) => {
        const [type, raw] = e.target.value.split(":");
        const id = Number(raw);
        const name =
          type === "user"
            ? people.find((m) => m.user.id === id)?.user.name
            : schedules.find((s) => s.id === id)?.name;
        if (name) onPick({ type: type as "user" | "schedule", id, name });
      }}
    >
      <option value="">+ Add target</option>
      <optgroup label="On-call schedules">
        {schedules.map((s) => (
          <option key={s.id} value={`schedule:${s.id}`} disabled={isTaken("schedule", s.id)}>
            {s.name}
          </option>
        ))}
      </optgroup>
      <optgroup label="People">
        {people.map((m) => (
          <option key={m.user.id} value={`user:${m.user.id}`} disabled={isTaken("user", m.user.id)}>
            {m.user.name}
          </option>
        ))}
      </optgroup>
    </select>
  );
}
