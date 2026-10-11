import { useState } from "react";
import { Card, PageHeader } from "@/components/Card";
import { Field, Input } from "@/components/Field";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/States";
import { useDocumentTitle } from "@/lib/hooks";
import { useAuditEvents } from "./hooks";

/** Read-only view of the append-only audit log, for the teams you administer. */
export function AuditLogPage() {
  useDocumentTitle("Audit log");
  const [action, setAction] = useState("");
  const events = useAuditEvents(action.trim());
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Security-relevant changes in the teams you administer. Entries can't be edited or deleted."
        actions={
          <Field label="Filter by action" className="w-56">
            {(props) => (
              <Input
                {...props}
                placeholder="e.g. service.key_rotated"
                value={action}
                onChange={(e) => setAction(e.target.value)}
              />
            )}
          </Field>
        }
      />
      <Card>
        {events.isPending ? (
          <div className="p-4">
            <SkeletonRows rows={6} />
          </div>
        ) : events.error ? (
          <ErrorState error={events.error} onRetry={() => void events.refetch()} />
        ) : events.data.results.length === 0 ? (
          <EmptyState title="No events">Nothing matches in the teams you administer.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">When</th>
                  <th className="px-4 py-2 font-medium">Action</th>
                  <th className="px-4 py-2 font-medium">Who</th>
                  <th className="px-4 py-2 font-medium">Target</th>
                  <th className="px-4 py-2 font-medium">From</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {events.data.results.map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-2 whitespace-nowrap tabular text-muted">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">{e.action}</td>
                    <td className="px-4 py-2">{e.actor_email || "system"}</td>
                    <td className="px-4 py-2 text-muted">
                      {e.target_type ? `${e.target_type} ${e.target_id}` : "-"}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-muted">{e.ip ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
