import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '../components/shared/PageHeader';
import { ErrorState } from '../components/shared/ErrorState';
import { IncidentTable } from '../components/incident/IncidentTable';
import { IncidentFilters as FilterBar } from '../components/incident/IncidentFilters';
import { useIncidents } from '../hooks/useIncidents';
import { IncidentFilters } from '../api/incidents';

export const Incidents: React.FC = () => {
  const [searchParams] = useSearchParams();

  // Extract and sanitize query filters from URL
  const filters = useMemo<IncidentFilters>(() => {
    const result: IncidentFilters = {};

    const status = searchParams.get('status');
    if (status && status !== 'all') {
      result.status = status;
    }

    const severity = searchParams.get('severity');
    if (severity && severity !== 'all') {
      result.severity = severity;
    }

    const service = searchParams.get('service');
    if (service && service !== 'all') {
      const parsedService = parseInt(service, 10);
      if (!isNaN(parsedService)) {
        result.service = parsedService;
      }
    }

    const active = searchParams.get('active');
    if (active === 'true') {
      result.active = true;
    } else if (active === 'false') {
      result.active = false;
    }

    return result;
  }, [searchParams]);

  const {
    data: incidents = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useIncidents(filters, { refetchInterval: 15_000 });

  const incidentList = useMemo(
    () => (Array.isArray(incidents) ? incidents : []),
    [incidents]
  );

  const activeCount = useMemo(
    () => incidentList.filter((i) => i.status?.toLowerCase() !== 'resolved').length,
    [incidentList]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <PageHeader
          title="Incident Workbench"
          description="Filter, inspect, and manage active and historical operational incidents."
        />

        <div className="flex items-center gap-3">
          <div className="px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs text-slate-300">
            Total: <span className="font-semibold text-white">{incidentList.length}</span>
          </div>
          <div className="px-3 py-1 rounded-full bg-indigo-950/80 border border-indigo-800 text-xs text-indigo-300">
            Active: <span className="font-semibold text-white">{activeCount}</span>
          </div>
        </div>
      </div>

      <FilterBar />

      {isError ? (
        <ErrorState
          title="Failed to load incidents"
          message={error instanceof Error ? error.message : 'Could not load incidents.'}
          onRetry={() => refetch()}
        />
      ) : (
        <IncidentTable
          incidents={incidentList}
          isLoading={isLoading}
          emptyMessage="No incidents found"
          emptyDescription="Try adjusting your filters or search criteria."
        />
      )}
    </div>
  );
};
