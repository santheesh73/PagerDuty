import React, { useState } from 'react';
import { Calendar, RefreshCw } from 'lucide-react';
import { AnalyticsRange } from '../types/analytics';
import {
  useAnalyticsSummary,
  useIncidentTrend,
  useIncidentsByService,
  useSeverityDistribution,
} from '../hooks/useAnalytics';
import { PageHeader } from '../components/shared/PageHeader';
import { Button } from '../components/shared/Button';
import { ErrorState } from '../components/shared/ErrorState';
import { AnalyticsKpis } from '../components/analytics/AnalyticsKpis';
import { ServiceBreakdown } from '../components/analytics/ServiceBreakdown';
import { SeverityDistribution } from '../components/analytics/SeverityDistribution';
import { IncidentTrendChart } from '../components/analytics/IncidentTrendChart';

export const Analytics: React.FC = () => {
  const [range, setRange] = useState<AnalyticsRange>('30d');

  // Independent queries for fault tolerance
  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
    refetch: refetchSummary,
  } = useAnalyticsSummary(range);

  const {
    data: serviceCounts,
    isLoading: serviceLoading,
    isError: serviceError,
    refetch: refetchServices,
  } = useIncidentsByService(range);

  const {
    data: severityCounts,
    isLoading: severityLoading,
    isError: severityError,
    refetch: refetchSeverity,
  } = useSeverityDistribution(range);

  const {
    data: trendPoints,
    isLoading: trendLoading,
    isError: trendError,
    refetch: refetchTrend,
  } = useIncidentTrend(range);

  const handleRefreshAll = () => {
    refetchSummary();
    refetchServices();
    refetchSeverity();
    refetchTrend();
  };

  const isAnyLoading = summaryLoading || serviceLoading || severityLoading || trendLoading;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Authoritative Mean Time to Acknowledge (MTTA), Mean Time to Resolve (MTTR), and system trends."
        actions={

          <div className="flex items-center gap-3">
            {/* Time Range Selector */}
            <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1">
              <span className="flex items-center gap-1 text-xs text-slate-400 px-2.5">
                <Calendar className="w-3.5 h-3.5 text-slate-500" />
                Range:
              </span>
              {(['7d', '30d', '90d'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRange(r)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    range === r
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`}
                >
                  {r === '7d' ? '7 Days' : r === '30d' ? '30 Days' : '90 Days'}
                </button>
              ))}
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={handleRefreshAll}
              disabled={isAnyLoading}
              aria-label="Refresh Analytics"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${isAnyLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {/* KPI Cards */}
      {summaryError ? (
        <ErrorState
          title="Failed to load KPI metrics"
          message="Could not retrieve summary metrics from the analytics engine."
          onRetry={() => refetchSummary()}
        />
      ) : (
        <AnalyticsKpis summary={summary} isLoading={summaryLoading} />
      )}

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Service Breakdown */}
        {serviceError ? (
          <ErrorState
            title="Failed to load service distribution"
            message="Could not retrieve incident service distribution."
            onRetry={() => refetchServices()}
          />
        ) : (
          <ServiceBreakdown data={serviceCounts} isLoading={serviceLoading} />
        )}

        {/* Severity Distribution */}
        {severityError ? (
          <ErrorState
            title="Failed to load severity distribution"
            message="Could not retrieve severity analytics."
            onRetry={() => refetchSeverity()}
          />
        ) : (
          <SeverityDistribution data={severityCounts} isLoading={severityLoading} />
        )}
      </div>

      {/* Daily Trend Chart */}
      {trendError ? (
        <ErrorState
          title="Failed to load incident trend"
          message="Could not retrieve daily trend volume."
          onRetry={() => refetchTrend()}
        />
      ) : (
        <IncidentTrendChart data={trendPoints} isLoading={trendLoading} />
      )}
    </div>
  );
};
