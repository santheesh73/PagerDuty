import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { CalendarClock, Plus } from "lucide-react";
import { ApiError } from "@/api/client";
import { Person } from "@/components/Avatar";
import { Button } from "@/components/Button";
import { Card, PageHeader } from "@/components/Card";
import { Dialog } from "@/components/Dialog";
import { Field, Input, Select } from "@/components/Field";
import { EmptyState, ErrorState, Skeleton } from "@/components/States";
import { useDocumentTitle } from "@/lib/hooks";
import { adminTeams, useMe } from "@/features/auth/hooks";
import { TIME_ZONES, useOnCallNow, useSaveSchedule, useSchedules } from "./hooks";

function OnCallNowCell({ id }: { id: number }) {
  const { data } = useOnCallNow(id);
  return <Person user={data?.user} muted="Nobody" />;
}

export function SchedulesPage() {
  useDocumentTitle("Schedules");
  const schedules = useSchedules();
  const { data: me } = useMe();
  const [creating, setCreating] = useState(false);
  const canCreate = adminTeams(me).length > 0;

  return (
    <>
      <PageHeader
        title="Schedules"
        description="Rotations decide who an escalation level pages. Times are kept in each schedule's own time zone."
        actions={
          canCreate && (
            <Button
              variant="primary"
              icon={<Plus className="size-4" />}
              onClick={() => setCreating(true)}
            >
              New schedule
            </Button>
          )
        }
      />
      {schedules.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : schedules.isError ? (
        <ErrorState error={schedules.error} onRetry={() => void schedules.refetch()} />
      ) : schedules.data.length === 0 ? (
        <EmptyState
          icon={<CalendarClock />}
          title="No schedules"
          action={
            canCreate && (
              <Button variant="primary" onClick={() => setCreating(true)}>
                Create a schedule
              </Button>
            )
          }
        >
          A schedule rotates responders daily, weekly or every few hours.
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {schedules.data.map((schedule) => (
            <li key={schedule.id}>
              <Card className="group relative p-4 hover:border-border-strong">
                <div className="flex items-start justify-between gap-2">
                  <Link
                    to={`/schedules/${schedule.id}`}
                    className="font-semibold after:absolute after:inset-0 group-hover:text-accent"
                  >
                    {schedule.name}
                  </Link>
                  <span className="text-xs text-muted">{schedule.timezone}</span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  {schedule.layers.length} {schedule.layers.length === 1 ? "layer" : "layers"} ·{" "}
                  {schedule.layers.map((l) => l.rotation_type).join(", ") || "no rotation yet"}
                </p>
                <div className="mt-3 flex items-center gap-2 text-sm">
                  <span className="text-xs text-muted">On call now</span>
                  <OnCallNowCell id={schedule.id} />
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <NewScheduleDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

function NewScheduleDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: me } = useMe();
  const teams = adminTeams(me);
  const save = useSaveSchedule();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [team, setTeam] = useState<number | undefined>();
  const [tz, setTz] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const error = save.error instanceof ApiError ? save.error : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New schedule"
      description="Add rotation layers after it's created."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!name.trim()}
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                { name: name.trim(), team: team ?? teams[0]?.id, timezone: tz, layers: [] },
                {
                  onSuccess: (s) => {
                    onClose();
                    navigate(`/schedules/${s.id}`);
                  },
                },
              )
            }
          >
            Create
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Name" error={error?.fieldError("name")}>
          {(p) => (
            <Input
              {...p}
              data-autofocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Payments primary"
            />
          )}
        </Field>
        {teams.length > 1 && (
          <Field label="Team">
            {(p) => (
              <Select
                {...p}
                value={team ?? teams[0]?.id}
                onChange={(e) => setTeam(Number(e.target.value))}
              >
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        <Field
          label="Time zone"
          hint="Handoffs happen at the same local time all year, DST included."
          error={error?.fieldError("timezone")}
        >
          {(p) => (
            <Select {...p} value={tz} onChange={(e) => setTz(e.target.value)}>
              {TIME_ZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
    </Dialog>
  );
}
