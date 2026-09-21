import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useServices } from '../../hooks/useServices';
import { Filter, X } from 'lucide-react';

export interface FilterValues {
  status?: string;
  severity?: string;
  service?: number;
  active?: boolean;
}

export interface IncidentFiltersProps {
  onFilterChange?: (filters: FilterValues) => void;
}

export const IncidentFilters: React.FC<IncidentFiltersProps> = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: services = [] } = useServices();

  const status = searchParams.get('status') || 'all';
  const severity = searchParams.get('severity') || 'all';
  const service = searchParams.get('service') || 'all';
  const active = searchParams.get('active') || 'all';

  const updateParam = (key: string, value: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (value === 'all' || !value) {
      nextParams.delete(key);
    } else {
      nextParams.set(key, value);
    }
    setSearchParams(nextParams);
  };

  const hasActiveFilters =
    status !== 'all' || severity !== 'all' || service !== 'all' || active !== 'all';

  const resetFilters = () => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('status');
    nextParams.delete('severity');
    nextParams.delete('service');
    nextParams.delete('active');
    setSearchParams(nextParams);
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 mb-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-medium text-slate-400 mr-1">
            <Filter className="w-3.5 h-3.5 text-slate-500" aria-hidden="true" />
            <span>Filters:</span>
          </div>

          {/* Status Filter */}
          <div>
            <label htmlFor="filter-status" className="sr-only">Status</label>
            <select
              id="filter-status"
              value={status}
              onChange={(e) => updateParam('status', e.target.value)}
              className="bg-slate-950 border border-slate-700/80 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="all">All Statuses</option>
              <option value="triggered">Triggered</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          {/* Severity Filter */}
          <div>
            <label htmlFor="filter-severity" className="sr-only">Severity</label>
            <select
              id="filter-severity"
              value={severity}
              onChange={(e) => updateParam('severity', e.target.value)}
              className="bg-slate-950 border border-slate-700/80 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          {/* Service Filter */}
          <div>
            <label htmlFor="filter-service" className="sr-only">Service</label>
            <select
              id="filter-service"
              value={service}
              onChange={(e) => updateParam('service', e.target.value)}
              className="bg-slate-950 border border-slate-700/80 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 max-w-[200px]"
            >
              <option value="all">All Services</option>
              {services.map((svc) => (
                <option key={svc.id} value={String(svc.id)}>
                  {svc.name}
                </option>
              ))}
            </select>
          </div>

          {/* Active State Filter */}
          <div>
            <label htmlFor="filter-active" className="sr-only">Active State</label>
            <select
              id="filter-active"
              value={active}
              onChange={(e) => updateParam('active', e.target.value)}
              className="bg-slate-950 border border-slate-700/80 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="all">Active & Resolved</option>
              <option value="true">Active Only</option>
              <option value="false">Resolved Only</option>
            </select>
          </div>
        </div>

        {/* Clear Filters Button */}
        {hasActiveFilters && (
          <button
            onClick={resetFilters}
            className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-3.5 h-3.5" aria-hidden="true" />
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
};
