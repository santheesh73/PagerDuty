import { Link } from "react-router";
import { BellRing, CheckCheck, Mail } from "lucide-react";
import { StatusBadge, UrgencyBadge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, PageHeader } from "@/components/Card";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/States";
import { Tabs } from "@/components/Tabs";
import { cn } from "@/lib/cn";
import { formatDateTime, formatRelative } from "@/lib/format";
import { useDocumentTitle, useNow } from "@/lib/hooks";
import type { IncidentStatus } from "@/api/types";
import { useSearchParams } from "react-router";
import { useMarkAllRead, useMarkRead, useNotifications, useUnreadCount } from "./hooks";

export function InboxPage() {
  useDocumentTitle("Notifications");
  const [params, setParams] = useSearchParams();
  const unreadOnly = params.get("filter") !== "all";
  const list = useNotifications(unreadOnly);
  const unread = useUnreadCount();
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  const now = useNow();

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Every page sent to you. Email copies go out at the same time."
        actions={
          <Button
            icon={<CheckCheck className="size-4" />}
            disabled={!unread.data?.count}
            loading={markAll.isPending}
            onClick={() => markAll.mutate()}
          >
            Mark all read
          </Button>
        }
      />
      <Tabs
        label="Filter"
        className="mb-4"
        items={[
          { key: "unread", label: "Unread", count: unread.data?.count },
          { key: "all", label: "All" },
        ]}
        value={unreadOnly ? "unread" : "all"}
        onChange={(key) => setParams(key === "all" ? { filter: "all" } : {}, { replace: true })}
      />
      {list.isPending ? (
        <SkeletonRows rows={5} />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState
          icon={<BellRing />}
          title={unreadOnly ? "You're all caught up" : "No notifications yet"}
        >
          {unreadOnly
            ? "New pages will show up here and on the bell."
            : "When an escalation pages you, it appears here."}
        </EmptyState>
      ) : (
        <Card>
          <ul className="divide-y divide-border">
            {list.data.results.map((n) => (
              <li
                key={n.id}
                className={cn(
                  "flex items-start gap-3 px-4 py-3",
                  !n.read_at && "bg-accent-soft/30",
                )}
              >
                <span
                  className={cn(
                    "mt-1.5 size-2 shrink-0 rounded-full",
                    n.read_at ? "bg-transparent" : "bg-accent",
                  )}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <UrgencyBadge urgency={n.incident.urgency} />
                    <Link
                      to={`/incidents/${n.incident.id}`}
                      onClick={() => !n.read_at && markRead.mutate(n.id)}
                      className="truncate font-medium hover:text-accent"
                    >
                      #{n.incident.number} {n.incident.title}
                    </Link>
                  </div>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <StatusBadge status={n.incident.status as IncidentStatus} />
                    <span title={formatDateTime(n.created_at)}>
                      Paged {formatRelative(n.created_at, now)}
                    </span>
                    {n.status === "dry_run" && (
                      <span className="font-medium text-accent">dry run</span>
                    )}
                    <span className="inline-flex items-center gap-1">
                      <Mail className="size-3" aria-hidden /> also emailed
                    </span>
                  </p>
                </div>
                {!n.read_at && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => markRead.mutate(n.id)}
                    aria-label={`Mark #${n.incident.number} as read`}
                  >
                    Mark read
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
