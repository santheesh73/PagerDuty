import { useState } from "react";
import { Link } from "react-router";
import { Boxes, Plus } from "lucide-react";
import { ModeBadge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, PageHeader } from "@/components/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/States";
import { useDocumentTitle } from "@/lib/hooks";
import { adminTeams, useMe } from "@/features/auth/hooks";
import { ServiceFormDialog } from "./ServiceForm";
import { useServices } from "./hooks";

export function ServicesPage() {
  useDocumentTitle("Services");
  const services = useServices();
  const { data: me } = useMe();
  const [creating, setCreating] = useState(false);
  const canCreate = adminTeams(me).length > 0;

  return (
    <>
      <PageHeader
        title="Services"
        description="Anything that can page someone. Each service has an integration key for the Events API and an escalation policy."
        actions={
          canCreate && (
            <Button
              variant="primary"
              icon={<Plus className="size-4" />}
              onClick={() => setCreating(true)}
            >
              New service
            </Button>
          )
        }
      />
      {services.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-36 rounded-xl" />
          ))}
        </div>
      ) : services.isError ? (
        <ErrorState error={services.error} onRetry={() => void services.refetch()} />
      ) : services.data.length === 0 ? (
        <EmptyState
          icon={<Boxes />}
          title="No services yet"
          action={
            canCreate && (
              <Button variant="primary" onClick={() => setCreating(true)}>
                Create a service
              </Button>
            )
          }
        >
          Create a service, point your monitoring at its integration key, then send a test alert.
        </EmptyState>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {services.data.map((service) => {
            const open = service.open_incidents.high + service.open_incidents.low;
            return (
              <li key={service.id}>
                <Card className="group relative flex h-full flex-col p-4 transition-colors hover:border-border-strong">
                  <div className="flex items-start justify-between gap-2">
                    <Link
                      to={`/services/${service.id}`}
                      className="font-semibold after:absolute after:inset-0 group-hover:text-accent"
                    >
                      {service.name}
                    </Link>
                    <ModeBadge mode={service.mode} />
                  </div>
                  <p className="mt-1 line-clamp-2 flex-1 text-sm text-muted">
                    {service.description || "No description"}
                  </p>
                  <div className="mt-4 flex items-center justify-between text-xs">
                    <span className="text-muted">{service.escalation_policy_name}</span>
                    {open > 0 ? (
                      <span className="tabular font-medium text-critical-fg">
                        {service.open_incidents.high > 0 && `${service.open_incidents.high} high`}
                        {service.open_incidents.high > 0 && service.open_incidents.low > 0 && " · "}
                        {service.open_incidents.low > 0 && `${service.open_incidents.low} low`} open
                      </span>
                    ) : (
                      <span className="text-good-fg">All clear</span>
                    )}
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
      <ServiceFormDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
