import React from 'react';
import { useHealth } from '../hooks/useHealth';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';

export const StatusPage: React.FC = () => {
  const { data, isLoading, isError, error, refetch, isFetching } = useHealth();

  const isConnected = !isLoading && !isError && (data?.status === 'ok' || data?.status === 'degraded');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-center items-center p-4">
      <div className="w-full max-w-xl space-y-6">
        <header className="text-center space-y-2">
          <div className="inline-block px-3 py-1 bg-indigo-950/60 border border-indigo-800/60 rounded-full text-xs font-semibold text-indigo-300 tracking-wide uppercase">
            Phase: 0 — Skeleton
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-white">
            Incident Management Platform
          </h1>
          <p className="text-sm text-slate-400">
            System Foundation & Infrastructure Verification
          </p>
        </header>

        <Card title="System Connectivity">
          <div className="space-y-4">
            <div className="flex items-center justify-between py-2 border-b border-slate-800">
              <span className="text-sm text-slate-300">Backend</span>
              {isLoading ? (
                <Badge variant="neutral">Connecting...</Badge>
              ) : isConnected ? (
                <Badge variant="success">Connected</Badge>
              ) : (
                <Badge variant="error">Unavailable</Badge>
              )}
            </div>

            <div className="flex items-center justify-between py-2 border-b border-slate-800">
              <span className="text-sm text-slate-300">Architecture</span>
              <span className="text-sm text-slate-400 font-mono">React 18 + Django 5 + PostgreSQL + Celery</span>
            </div>

            <div className="flex items-center justify-between py-2 border-b border-slate-800">
              <span className="text-sm text-slate-300">Phase Status</span>
              <span className="text-sm text-emerald-400 font-medium">Phase 0: Skeleton Active</span>
            </div>

            {data?.dependencies && (
              <div className="pt-2 space-y-2">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Infrastructure Dependencies
                </span>
                <div className="grid grid-cols-2 gap-2 pt-1">
                  {Object.entries(data.dependencies).map(([dep, status]) => (
                    <div
                      key={dep}
                      className="bg-slate-950/50 border border-slate-800/80 rounded-lg p-2.5 flex items-center justify-between text-xs"
                    >
                      <span className="capitalize text-slate-300">{dep}</span>
                      <Badge variant={status === 'ok' ? 'success' : 'warning'}>
                        {status}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {isError && (
              <div className="p-3 bg-rose-950/40 border border-rose-900/60 rounded-lg text-xs text-rose-300">
                {error?.message || 'Unable to connect to backend service.'}
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => refetch()}
                disabled={isFetching}
                className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900 disabled:text-indigo-400 text-white text-xs font-medium rounded-lg transition-colors shadow-sm"
              >
                {isFetching ? 'Refreshing...' : 'Recheck Health'}
              </button>
            </div>
          </div>
        </Card>

        <footer className="text-center text-xs text-slate-500">
          Ready for Phase 1 (Users, Teams & Identity Domain)
        </footer>
      </div>
    </div>
  );
};
