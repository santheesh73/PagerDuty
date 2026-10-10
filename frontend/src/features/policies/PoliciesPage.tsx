import { Link } from "react-router";
import { Plus, Workflow } from "lucide-react";
import { Avatar } from "@/components/Avatar";
import { Button } from "@/components/Button";
import { Card, PageHeader } from "@/components/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/States";
import { useDocumentTitle } from "@/lib/hooks";
import { adminTeams, useMe } from "@/features/auth/hooks";
import { useOnCalls, usePolicies } from "./hooks";

export function PoliciesPage() {
  useDocumentTitle("Escalation policies");
  const policies = usePolicies();
  const oncalls = useOnCalls();
  const { data: me } = useMe();
  const canCreate = adminTeams(me).length > 0;
  const nowFor = (policyId: number) =>
    oncalls.data?.find((p) => p.policy.id === policyId)?.levels[0]?.oncall ?? [];

  return (
    <>
      <PageHeader
        title="Escalation policies"
        description="Who gets paged, in what order, and how long each level has to respond."
        actions={
          canCreate && (
            <Link to="/escalation-policies/new">
              <Button variant="primary" icon={<Plus className="size-4" />}>
                New policy
              </Button>
            </Link>
          )
        }
      />
      {policies.isPending ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : policies.isError ? (
        <ErrorState error={policies.error} onRetry={() => void policies.refetch()} />
      ) : policies.data.length === 0 ? (
        <EmptyState
          icon={<Workflow />}
          title="No escalation policies"
          action={
            canCreate && (
              <Link to="/escalation-policies/new">
                <Button variant="primary">Create a policy</Button>
              </Link>
            )
          }
        >
          A policy decides who is paged first and who comes next if nobody responds.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {policies.data.map((policy) => (
            <li key={policy.id}>
              <Card className="group relative flex flex-wrap items-center gap-4 p-4 hover:border-border-strong">
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/escalation-policies/${policy.id}`}
                    className="font-semibold after:absolute after:inset-0 group-hover:text-accent"
                  >
                    {policy.name}
                  </Link>
                  <p className="mt-1 text-xs text-muted">
                    {policy.rules.length} {policy.rules.length === 1 ? "level" : "levels"}
                    {policy.num_loops > 0 && ` · repeats ${policy.num_loops}×`}
                    {" · "}used by{" "}
                    {policy.services.length
                      ? policy.services.map((s) => s.name).join(", ")
                      : "no services"}
                  </p>
                </div>
                <ol className="flex items-center gap-1 text-xs text-muted" aria-label="Levels">
                  {policy.rules.map((rule, i) => (
                    <li key={rule.level} className="flex items-center gap-1">
                      {i > 0 && (
                        <span aria-hidden className="text-subtle">
                          → {policy.rules[i - 1]!.delay_minutes}m →
                        </span>
                      )}
                      <span className="rounded-md bg-surface-2 px-2 py-1">
                        {rule.targets.map((t) => t.name).join(", ")}
                      </span>
                    </li>
                  ))}
                </ol>
                <div className="flex items-center gap-2 text-xs text-muted">
                  On call now
                  {nowFor(policy.id)
                    .filter((e) => e.user)
                    .map((e) => (
                      <Avatar key={e.user!.id} user={e.user!} size="sm" />
                    ))}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
