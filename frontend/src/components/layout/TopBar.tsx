import React from 'react';
import { useHealth } from '../../hooks/useHealth';
import { Badge } from '../shared/Badge';
import { ShieldCheck, RefreshCw, Menu } from 'lucide-react';

export interface TopBarProps {
  onOpenMobileMenu?: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({ onOpenMobileMenu }) => {
  const { data, isLoading, isError, isFetching, refetch } = useHealth();

  const isConnected = !isLoading && !isError && (data?.status === 'ok' || data?.status === 'degraded');

  return (
    <header className="h-16 bg-slate-900/80 backdrop-blur border-b border-slate-800 px-4 sm:px-6 flex items-center justify-between sticky top-0 z-30">
      <div className="flex items-center gap-3">
        {/* Mobile menu toggle button */}
        <button
          type="button"
          onClick={onOpenMobileMenu}
          aria-label="Open navigation menu"
          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg md:hidden transition-colors"
        >
          <Menu className="w-5 h-5" aria-hidden="true" />
        </button>

        <h2 className="text-sm font-semibold text-slate-200">
          Operations Center
        </h2>
      </div>

      <div className="flex items-center gap-3">
        {/* Backend API Connection Status */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 hidden sm:inline">API:</span>
          {isLoading ? (
            <Badge variant="neutral">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-pulse" />
              Connecting...
            </Badge>
          ) : isConnected ? (
            <Badge variant="success">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Connected
            </Badge>
          ) : (
            <Badge variant="error">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
              Unavailable
            </Badge>
          )}

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            title="Recheck API health"
            aria-label="Recheck API health"
            className="p-1 text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-50"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin text-indigo-400' : ''}`}
              aria-hidden="true"
            />
          </button>
        </div>

        <div className="h-4 w-px bg-slate-800" aria-hidden="true" />

        <div className="flex items-center gap-2 text-xs text-slate-400">
          <ShieldCheck className="w-4 h-4 text-indigo-400" aria-hidden="true" />
          <span className="hidden md:inline font-medium">Production Platform</span>
        </div>
      </div>
    </header>
  );
};
