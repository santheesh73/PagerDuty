import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Globe,
  Pencil,
  Plus,
  Trash2,
  UserRoundPlus,
  X,
} from "lucide-react";
import { ApiError } from "@/api/client";
import type { Layer, LayerInput, Schedule } from "@/api/types";
import { Avatar, Person } from "@/components/Avatar";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader } from "@/components/Card";
import { Dialog } from "@/components/Dialog";
import { Field, Input, Select } from "@/components/Field";
import { EmptyState, ErrorState, Skeleton } from "@/components/States";
import { formatDateTime } from "@/lib/format";
import { useDocumentTitle, useNow } from "@/lib/hooks";
import { dayStartsIn } from "@/lib/time";
import { hasRole, useMe } from "@/features/auth/hooks";
import { useTeamMembers } from "@/features/services/hooks";
import {
  MAX_LAYERS,
  MAX_MEMBERS,
  useCreateOverride,
  useDeleteOverride,
  useOnCallNow,
  useOverrides,
  useSaveSchedule,
  useSchedule,
  useShifts,
} from "./hooks";
import { ShiftTimeline } from "./ShiftTimeline";

const DAYS = 7;

export function SchedulePage() {
  const id = Number(useParams().id);
  const schedule = useSchedule(id);
  const { data: me } = useMe();
  useDocumentTitle(schedule.data?.name ?? "Schedule");

  if (schedule.isPending) return <Skeleton className="h-80 rounded-xl" />;
  if (schedule.isError)
    return <ErrorState error={schedule.error} onRetry={() => void schedule.refetch()} />;
  const data = schedule.data;
  const isAdmin = hasRole(me, data.team, "admin");

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1 text-sm text-muted">
        <Link to="/schedules" className="hover:text-text">
          Schedules
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="text-text">{data.name}</span>
      </nav>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{data.name}</h1>
          <p className="mt-1 inline-flex items-center gap-1.5 text-muted">
            <Globe className="size-3.5" aria-hidden /> Times shown in {data.timezone}
          </p>
        </div>
        <OnCallNowBadge id={id} />
      </div>
      <WeekView schedule={data} />
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Layers schedule={data} isAdmin={isAdmin} />
        <Overrides schedule={data} isAdmin={isAdmin} />
      </div>
    </>
  );
}

function OnCallNowBadge({ id }: { id: number }) {
  const { data } = useOnCallNow(id);
  if (!data) return null;
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 shadow-card">
      <span className="text-xs text-muted">On call now</span>
      <Person user={data.user} muted="Nobody" />
      {data.source === "override" && <Badge tone="info">override</Badge>}
    </div>
  );
}

function WeekView({ schedule }: { schedule: Schedule }) {
  const [offset, setOffset] = useState(0);
  const now = useNow(60_000);
  // Lay the week out on the schedule's own local midnights, not the browser's. Same day →
  // same instants, so the shifts query key only changes when the date does.
  const dayStarts = useMemo(
    () => dayStartsIn(new Date(now + offset * DAYS * 86_400_000), DAYS, schedule.timezone),
    [now, offset, schedule.timezone],
  );
  const since = dayStarts[0]!;
  const until = dayStarts[DAYS]!;
  const shifts = useShifts(schedule.id, since, until);

  return (
    <Card>
      <CardHeader
        title="Who's on call"
        description="The final schedule after layers and overrides"
        action={
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              aria-label="Previous week"
              onClick={() => setOffset((o) => o - 1)}
              icon={<ChevronLeft className="size-4" />}
            />
            <Button
              size="sm"
              variant={offset === 0 ? "secondary" : "ghost"}
              onClick={() => setOffset(0)}
            >
              This week
            </Button>
            <Button
              size="sm"
              variant="ghost"
              aria-label="Next week"
              onClick={() => setOffset((o) => o + 1)}
              icon={<ChevronRight className="size-4" />}
            />
          </div>
        }
      />
      <div className="p-4">
        {shifts.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : shifts.isError ? (
          <ErrorState error={shifts.error} onRetry={() => void shifts.refetch()} />
        ) : shifts.data.length === 0 ? (
          <EmptyState title="Nobody is on call this week">
            Add a rotation layer with at least one person.
          </EmptyState>
        ) : (
          <ShiftTimeline
            shifts={shifts.data}
            dayStarts={dayStarts}
            timeZone={schedule.timezone}
            now={now}
          />
        )}
      </div>
    </Card>
  );
}

function describeRotation(layer: Layer): string {
  if (layer.rotation_type === "custom") return `Every ${layer.turn_length_hours}h`;
  const unit = layer.rotation_type === "weekly" ? "week" : "day";
  const turn = layer.turn_count === 1 ? `Every ${unit}` : `Every ${layer.turn_count} ${unit}s`;
  return `${turn} at ${layer.handoff_time.slice(0, 5)}`;
}

function layerInput(layer: Layer): LayerInput {
  return {
    name: layer.name,
    rotation_type: layer.rotation_type,
    turn_count: layer.turn_count,
    turn_length_hours: layer.turn_length_hours,
    start: layer.start,
    handoff_time: layer.handoff_time,
    members: layer.members,
  };
}

function Layers({ schedule, isAdmin }: { schedule: Schedule; isAdmin: boolean }) {
  const save = useSaveSchedule(schedule.id);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const layers = schedule.layers;

  const saveLayers = (next: LayerInput[], onDone?: () => void) =>
    save.mutate({ layers: next }, { onSuccess: () => onDone?.() });
  const moveLayer = (index: number, by: number) => {
    const next = layers.map(layerInput);
    const [item] = next.splice(index, 1);
    next.splice(index + by, 0, item!);
    saveLayers(next);
  };

  return (
    <Card>
      <CardHeader
        title="Rotation layers"
        description="Higher layers win when more than one has someone on call."
        action={
          isAdmin && (
            <Button
              size="sm"
              icon={<Plus className="size-3.5" />}
              disabled={layers.length >= MAX_LAYERS}
              onClick={() => setEditing("new")}
            >
              Add layer
            </Button>
          )
        }
      />
      {layers.length === 0 ? (
        <div className="p-4">
          <EmptyState title="No layers yet">
            Add a layer to start rotating people on call.
          </EmptyState>
        </div>
      ) : (
        <ol className="divide-y divide-border">
          {layers.map((layer, index) => (
            <li key={layer.id} className="flex flex-wrap items-start gap-3 px-4 py-3">
              <span
                className="mt-0.5 grid size-6 place-items-center rounded-full bg-surface-2 text-xs font-semibold text-muted"
                title="Priority"
              >
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium">{layer.name}</p>
                <p className="text-xs text-muted">
                  {describeRotation(layer)} · since {formatDateTime(layer.start, schedule.timezone)}
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {layer.member_details.map((m, i) => (
                    <span
                      key={`${m.id}-${i}`}
                      className="inline-flex items-center gap-1 rounded-full bg-surface-2 py-0.5 pr-2 pl-0.5 text-xs"
                    >
                      <Avatar user={m} size="sm" /> {m.name}
                    </span>
                  ))}
                </div>
              </div>
              {isAdmin && (
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Raise ${layer.name}`}
                    disabled={index === 0 || save.isPending}
                    onClick={() => moveLayer(index, -1)}
                    icon={<ArrowUp className="size-3.5" />}
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Lower ${layer.name}`}
                    disabled={index === layers.length - 1 || save.isPending}
                    onClick={() => moveLayer(index, 1)}
                    icon={<ArrowDown className="size-3.5" />}
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Edit ${layer.name}`}
                    onClick={() => setEditing(index)}
                    icon={<Pencil className="size-3.5" />}
                  />
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Delete ${layer.name}`}
                    disabled={save.isPending}
                    onClick={() => saveLayers(layers.filter((_, i) => i !== index).map(layerInput))}
                    icon={<Trash2 className="size-3.5" />}
                  />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      {editing !== null && (
        <LayerDialog
          schedule={schedule}
          layer={editing === "new" ? undefined : layers[editing]}
          saving={save.isPending}
          error={save.error instanceof ApiError ? save.error : null}
          onClose={() => {
            setEditing(null);
            save.reset();
          }}
          onSave={(input) => {
            const next = layers.map(layerInput);
            if (editing === "new") next.push(input);
            else next[editing] = input;
            saveLayers(next, () => setEditing(null));
          }}
        />
      )}
    </Card>
  );
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function LayerDialog({
  schedule,
  layer,
  saving,
  error,
  onClose,
  onSave,
}: {
  schedule: Schedule;
  layer?: Layer;
  saving: boolean;
  error: ApiError | null;
  onClose: () => void;
  onSave: (input: LayerInput) => void;
}) {
  const members = useTeamMembers(schedule.team);
  const [form, setForm] = useState(() => ({
    name: layer?.name ?? "Primary",
    rotation_type: layer?.rotation_type ?? "weekly",
    turn_count: layer?.turn_count ?? 1,
    turn_length_hours: layer?.turn_length_hours ?? 12,
    start: toLocalInput(layer?.start ?? new Date().toISOString()),
    handoff_time: (layer?.handoff_time ?? "09:00:00").slice(0, 5),
    members: layer?.member_details ?? [],
  }));
  const [pick, setPick] = useState("");
  const eligible = (members.data ?? []).filter((m) => m.role !== "viewer");
  const custom = form.rotation_type === "custom";

  const move = (index: number, by: number) => {
    const next = [...form.members];
    const [item] = next.splice(index, 1);
    next.splice(index + by, 0, item!);
    setForm({ ...form, members: next });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      variant="drawer"
      title={layer ? `Edit ${layer.name}` : "New layer"}
      description={`Handoff times are in ${schedule.timezone}.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={saving}
            disabled={!form.name.trim()}
            onClick={() =>
              onSave({
                name: form.name.trim(),
                rotation_type: form.rotation_type,
                turn_count: form.turn_count,
                turn_length_hours: custom ? form.turn_length_hours : null,
                start: new Date(form.start).toISOString(),
                handoff_time: `${form.handoff_time}:00`,
                members: form.members.map((m) => m.id),
              })
            }
          >
            Save layer
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <p
            role="alert"
            className="rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical-fg"
          >
            {error.message}
          </p>
        )}
        <Field label="Name">
          {(p) => (
            <Input
              {...p}
              data-autofocus
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          )}
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Rotation">
            {(p) => (
              <Select
                {...p}
                value={form.rotation_type}
                onChange={(e) =>
                  setForm({ ...form, rotation_type: e.target.value as LayerInput["rotation_type"] })
                }
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="custom">Custom (hours)</option>
              </Select>
            )}
          </Field>
          {custom ? (
            <Field label="Hours per turn">
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  min={1}
                  max={672}
                  value={form.turn_length_hours}
                  onChange={(e) => setForm({ ...form, turn_length_hours: e.target.valueAsNumber })}
                />
              )}
            </Field>
          ) : (
            <Field label={form.rotation_type === "weekly" ? "Weeks per turn" : "Days per turn"}>
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  min={1}
                  max={52}
                  value={form.turn_count}
                  onChange={(e) => setForm({ ...form, turn_count: e.target.valueAsNumber })}
                />
              )}
            </Field>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Starts (your local time)">
            {(p) => (
              <Input
                {...p}
                type="datetime-local"
                value={form.start}
                onChange={(e) => setForm({ ...form, start: e.target.value })}
              />
            )}
          </Field>
          <Field
            label={`Handoff (${schedule.timezone})`}
            hint={custom ? "Not used for custom rotations" : undefined}
          >
            {(p) => (
              <Input
                {...p}
                type="time"
                disabled={custom}
                value={form.handoff_time}
                onChange={(e) => setForm({ ...form, handoff_time: e.target.value })}
              />
            )}
          </Field>
        </div>
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted">
            Rotation order ({form.members.length} / {MAX_MEMBERS})
          </p>
          <ol className="space-y-1">
            {form.members.map((m, i) => (
              <li
                key={`${m.id}-${i}`}
                className="flex items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-sm"
              >
                <span className="w-5 text-xs text-subtle">{i + 1}</span>
                <Avatar user={m} size="sm" />
                <span className="flex-1 truncate">{m.name}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Move ${m.name} up`}
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                  icon={<ArrowUp className="size-3.5" />}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Move ${m.name} down`}
                  disabled={i === form.members.length - 1}
                  onClick={() => move(i, 1)}
                  icon={<ArrowDown className="size-3.5" />}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Remove ${m.name}`}
                  onClick={() =>
                    setForm({ ...form, members: form.members.filter((_, j) => j !== i) })
                  }
                  icon={<X className="size-3.5" />}
                />
              </li>
            ))}
          </ol>
          <div className="mt-2 flex gap-2">
            <Select
              aria-label="Person to add"
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              disabled={form.members.length >= MAX_MEMBERS}
            >
              <option value="">Add a person…</option>
              {eligible.map((m) => (
                <option key={m.user.id} value={m.user.id}>
                  {m.user.name}
                </option>
              ))}
            </Select>
            <Button
              icon={<UserRoundPlus className="size-4" />}
              disabled={!pick}
              onClick={() => {
                const user = eligible.find((m) => String(m.user.id) === pick)?.user;
                if (user) setForm({ ...form, members: [...form.members, user] });
                setPick("");
              }}
            >
              Add
            </Button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}

function Overrides({ schedule, isAdmin }: { schedule: Schedule; isAdmin: boolean }) {
  const overrides = useOverrides(schedule.id);
  const remove = useDeleteOverride(schedule.id);
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader
        title="Overrides"
        description="Swap someone in for a window. The latest override wins."
        action={
          isAdmin && (
            <Button size="sm" icon={<Plus className="size-3.5" />} onClick={() => setOpen(true)}>
              Add
            </Button>
          )
        }
      />
      <div className="p-4">
        {overrides.isPending ? (
          <Skeleton className="h-16" />
        ) : overrides.isError ? (
          <ErrorState error={overrides.error} onRetry={() => void overrides.refetch()} />
        ) : overrides.data.length === 0 ? (
          <p className="text-sm text-muted">No upcoming overrides.</p>
        ) : (
          <ul className="space-y-2">
            {overrides.data.map((o) => (
              <li
                key={o.id}
                className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
              >
                <Person user={o.user_detail} />
                <span className="ml-auto text-right text-xs text-muted">
                  {formatDateTime(o.start, schedule.timezone)}
                  <br />→ {formatDateTime(o.end, schedule.timezone)}
                </span>
                {isAdmin && (
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Remove override for ${o.user_detail.name}`}
                    loading={remove.isPending && remove.variables === o.id}
                    onClick={() => remove.mutate(o.id)}
                    icon={<Trash2 className="size-3.5" />}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {open && <OverrideDrawer schedule={schedule} onClose={() => setOpen(false)} />}
    </Card>
  );
}

function OverrideDrawer({ schedule, onClose }: { schedule: Schedule; onClose: () => void }) {
  const members = useTeamMembers(schedule.team);
  const create = useCreateOverride(schedule.id);
  const hour = new Date();
  hour.setMinutes(0, 0, 0);
  const [form, setForm] = useState({
    user: "",
    start: toLocalInput(new Date(hour.getTime() + 3_600_000).toISOString()),
    end: toLocalInput(new Date(hour.getTime() + 5 * 3_600_000).toISOString()),
  });
  const error = create.error instanceof ApiError ? create.error : null;
  return (
    <Dialog
      open
      onClose={onClose}
      variant="drawer"
      title="Add override"
      description="Times are in your local time zone."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!form.user}
            loading={create.isPending}
            onClick={() =>
              create.mutate(
                {
                  user: Number(form.user),
                  start: new Date(form.start).toISOString(),
                  end: new Date(form.end).toISOString(),
                },
                { onSuccess: onClose },
              )
            }
          >
            Add override
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Who covers" error={error?.fieldError("user")}>
          {(p) => (
            <Select
              {...p}
              data-autofocus
              value={form.user}
              onChange={(e) => setForm({ ...form, user: e.target.value })}
            >
              <option value="">Choose a person…</option>
              {(members.data ?? [])
                .filter((m) => m.role !== "viewer")
                .map((m) => (
                  <option key={m.user.id} value={m.user.id}>
                    {m.user.name}
                  </option>
                ))}
            </Select>
          )}
        </Field>
        <Field label="From">
          {(p) => (
            <Input
              {...p}
              type="datetime-local"
              value={form.start}
              onChange={(e) => setForm({ ...form, start: e.target.value })}
            />
          )}
        </Field>
        <Field label="Until" error={error?.fieldError("end")}>
          {(p) => (
            <Input
              {...p}
              type="datetime-local"
              value={form.end}
              onChange={(e) => setForm({ ...form, end: e.target.value })}
            />
          )}
        </Field>
      </div>
    </Dialog>
  );
}
