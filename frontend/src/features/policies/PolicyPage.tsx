import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ChevronRight, Trash2 } from "lucide-react";
import { ApiError } from "@/api/client";
import type { EscalationPolicy } from "@/api/types";
import { Button } from "@/components/Button";
import { Field, Select } from "@/components/Field";
import { ErrorState, Skeleton } from "@/components/States";
import { useDocumentTitle } from "@/lib/hooks";
import { adminTeams, hasRole, useMe } from "@/features/auth/hooks";
import { useSchedules } from "@/features/schedules/hooks";
import { useTeamMembers } from "@/features/services/hooks";
import { draftFrom, toPayload, validate } from "./draft";
import { useDeletePolicy, usePolicy, useSavePolicy } from "./hooks";
import { PolicyEditor } from "./PolicyEditor";

/** Loads the policy (or picks a team for a new one), then mounts a form keyed to it. */
export function PolicyPage() {
  const params = useParams();
  const isNew = params.id === "new";
  const id = isNew ? undefined : Number(params.id);
  const policy = usePolicy(id);
  const { data: me } = useMe();
  const teams = adminTeams(me);
  const [teamChoice, setTeamChoice] = useState<number | undefined>();
  const team = policy.data?.team ?? teamChoice ?? teams[0]?.id;
  useDocumentTitle(isNew ? "New policy" : (policy.data?.name ?? "Policy"));

  if (!isNew && policy.isPending) return <Skeleton className="h-96 rounded-xl" />;
  if (!isNew && policy.isError)
    return <ErrorState error={policy.error} onRetry={() => void policy.refetch()} />;
  if (team === undefined) {
    return (
      <ErrorState
        error={new ApiError(403, "no_team", "You need to be a team admin to create policies.")}
      />
    );
  }
  return (
    <PolicyForm
      key={`${id ?? "new"}-${team}`}
      policy={policy.data}
      team={team}
      teamPicker={
        isNew && teams.length > 1 ? (
          <Field label="Team" className="mb-5 max-w-xs">
            {(props) => (
              <Select
                {...props}
                value={team}
                onChange={(e) => setTeamChoice(Number(e.target.value))}
              >
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        ) : null
      }
    />
  );
}

function PolicyForm({
  policy,
  team,
  teamPicker,
}: {
  policy: EscalationPolicy | undefined;
  team: number;
  teamPicker: React.ReactNode;
}) {
  const isNew = !policy;
  const [draft, setDraft] = useState(() => draftFrom(policy, team));
  const [problem, setProblem] = useState<string | null>(null);
  const { data: me } = useMe();
  const members = useTeamMembers(team);
  const schedules = useSchedules();
  const save = useSavePolicy(policy?.id);
  const remove = useDeletePolicy();
  const navigate = useNavigate();
  const teamSchedules = useMemo(
    () => schedules.data?.filter((s) => s.team === team) ?? [],
    [schedules.data, team],
  );
  const canEdit = hasRole(me, team, "admin");
  const apiError = save.error instanceof ApiError ? save.error : null;

  const onSave = () => {
    const message = validate(draft);
    setProblem(message);
    if (message) return;
    save.mutate(toPayload(draft), {
      onSuccess: (saved) =>
        isNew && navigate(`/escalation-policies/${saved.id}`, { replace: true }),
    });
  };

  return (
    <div className="max-w-3xl">
      <nav aria-label="Breadcrumb" className="mb-3 flex items-center gap-1 text-sm text-muted">
        <Link to="/escalation-policies" className="hover:text-text">
          Escalation policies
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="text-text">{isNew ? "New" : policy.name}</span>
      </nav>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {isNew ? "New escalation policy" : draft.name || "Untitled policy"}
          </h1>
          <p className="mt-1 text-muted">
            Changes apply to new incidents. Open incidents keep the policy they started with.
            {!canEdit && " You can view this policy; only team admins can change it."}
          </p>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            {!isNew && (
              <Button
                variant="ghost"
                icon={<Trash2 className="size-4" />}
                loading={remove.isPending}
                onClick={() =>
                  remove.mutate(policy.id, { onSuccess: () => navigate("/escalation-policies") })
                }
              >
                Delete
              </Button>
            )}
            <Button variant="primary" loading={save.isPending} onClick={onSave}>
              {isNew ? "Create policy" : "Save changes"}
            </Button>
          </div>
        )}
      </div>
      {teamPicker}
      {(problem || (apiError && !apiError.fieldError("name"))) && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-critical/30 bg-critical-soft px-3 py-2 text-sm text-critical-fg"
        >
          {problem ?? apiError?.message}
        </p>
      )}
      <PolicyEditor
        draft={draft}
        onChange={setDraft}
        members={members.data ?? []}
        schedules={teamSchedules}
        readOnly={!canEdit}
        error={apiError}
      />
    </div>
  );
}
