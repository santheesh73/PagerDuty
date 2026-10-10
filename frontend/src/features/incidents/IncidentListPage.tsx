import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { CheckCircle2, Search } from "lucide-react";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/Card";
import { Input, Select } from "@/components/Field";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/States";
import { Tabs } from "@/components/Tabs";
import { useDocumentTitle } from "@/lib/hooks";
import { useServices } from "@/features/services/hooks";
import { IncidentTable } from "./components";
import { flattenPages, useIncidents } from "./hooks";

const TABS = [
  { key: "open", label: "Open", status: "triggered,acknowledged" },
  { key: "triggered", label: "Triggered", status: "triggered" },
  { key: "acknowledged", label: "Acknowledged", status: "acknowledged" },
  { key: "resolved", label: "Resolved", status: "resolved" },
  { key: "all", label: "All", status: "" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function IncidentListPage() {
  useDocumentTitle("Incidents");
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.key === params.get("tab"))?.key ?? "open") as TabKey;
  const urgency = params.get("urgency") ?? "";
  const service = params.get("service") ?? "";
  const mine = params.get("assignee") === "me";
  const search = params.get("q") ?? "";
  const [draft, setDraft] = useState(search);

  // Filters live in the URL so a view can be shared or bookmarked; search is debounced.
  const update = (patch: Record<string, string | null>) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(patch)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      },
      { replace: true },
    );
  useEffect(() => {
    if (draft === search) return;
    const id = window.setTimeout(() => update({ q: draft || null }), 300);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- update is stable in effect
  }, [draft]);

  const status = TABS.find((t) => t.key === tab)!.status;
  const query = useIncidents({
    status: status || undefined,
    urgency: urgency || undefined,
    service: service || undefined,
    assignee: mine ? "me" : undefined,
    search: search || undefined,
  });
  const services = useServices();
  const incidents = flattenPages(query.data);
  const filtered = Boolean(urgency || service || mine || search);

  return (
    <>
      <PageHeader
        title="Incidents"
        description="Everything that paged, is paging, or was resolved. Updates every 10 seconds."
      />
      <Tabs
        label="Incident status"
        items={TABS.map((t) => ({ key: t.key, label: t.label }))}
        value={tab}
        onChange={(key) => update({ tab: key === "open" ? null : key })}
      />
      <div className="my-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search
            className="pointer-events-none absolute top-2.5 left-3 size-4 text-subtle"
            aria-hidden
          />
          <Input
            aria-label="Search incidents"
            placeholder="Search title, #number or dedup key"
            className="pl-9"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </div>
        <Select
          aria-label="Urgency"
          className="w-36"
          value={urgency}
          onChange={(e) => update({ urgency: e.target.value || null })}
        >
          <option value="">Any urgency</option>
          <option value="high">High urgency</option>
          <option value="low">Low urgency</option>
        </Select>
        <Select
          aria-label="Service"
          className="w-44"
          value={service}
          onChange={(e) => update({ service: e.target.value || null })}
        >
          <option value="">All services</option>
          {services.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <Button
          variant={mine ? "primary" : "secondary"}
          aria-pressed={mine}
          onClick={() => update({ assignee: mine ? null : "me" })}
        >
          Assigned to me
        </Button>
      </div>

      {query.isPending ? (
        <SkeletonRows rows={6} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : incidents.length === 0 ? (
        filtered ? (
          <EmptyState
            title="No incidents match these filters"
            action={
              <Button
                onClick={() => {
                  setDraft("");
                  setParams({ tab: tab === "open" ? "" : tab });
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={<CheckCircle2 />}
            title={tab === "resolved" ? "Nothing resolved yet" : "All quiet"}
            action={
              <Link to="/services">
                <Button variant="primary">Send a test alert</Button>
              </Link>
            }
          >
            No {tab === "all" ? "" : `${tab} `}incidents. Send a test alert from a service to see
            the whole flow: page, escalate, acknowledge, resolve.
          </EmptyState>
        )
      ) : (
        <>
          <IncidentTable incidents={incidents} />
          {query.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
