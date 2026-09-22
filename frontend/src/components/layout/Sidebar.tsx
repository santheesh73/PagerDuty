import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  AlertTriangle,
  Layers,
  Calendar,
  GitBranch,
  BarChart3,
  Flame,
  X,
} from 'lucide-react';
import { cn } from '../../lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  exact?: boolean;
}

const navItems: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { to: '/incidents', label: 'Incidents', icon: AlertTriangle },
  { to: '/services', label: 'Services', icon: Layers },
  { to: '/on-call', label: 'On-call', icon: Calendar },
  { to: '/escalation-policies', label: 'Escalation Policies', icon: GitBranch },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
];

export interface SidebarProps {
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  mobileOpen = false,
  onCloseMobile,
}) => {
  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-40 md:hidden animate-in fade-in duration-150"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      {/* Main Sidebar (Fixed slide-over on mobile, static on desktop) */}
      <aside
        className={cn(
          'fixed md:static inset-y-0 left-0 z-50 w-64 bg-slate-900 border-r border-slate-800 flex flex-col shrink-0 min-h-screen transition-transform duration-200 ease-in-out',
          mobileOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full md:translate-x-0'
        )}
      >
        {/* Brand Header */}
        <div className="h-16 flex items-center justify-between px-6 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm">
              <Flame className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <span className="font-bold text-sm tracking-tight text-white block">IncidentPlatform</span>
              <span className="text-[10px] text-slate-400 font-mono block uppercase">Core Workbench</span>
            </div>
          </div>

          {/* Close button on mobile */}
          <button
            type="button"
            onClick={onCloseMobile}
            aria-label="Close navigation menu"
            className="p-1 text-slate-400 hover:text-white rounded-lg md:hidden hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 py-4 px-3 space-y-1" aria-label="Main Navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.exact}
                onClick={onCloseMobile}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500',
                    isActive
                      ? 'bg-indigo-600/15 text-indigo-400 font-semibold border-l-2 border-indigo-500 rounded-l-none'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  )
                }
              >
                <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Platform Status & Environment Footer */}
        <div className="p-4 border-t border-slate-800/80 text-[11px] text-slate-500 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span>Core Services</span>
            <span className="text-emerald-400 font-mono flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Operational
            </span>
          </div>
          <div className="text-[10px] text-slate-600 font-mono pt-0.5">
            IncidentPlatform v1.0 • Phase 6 Ready
          </div>
        </div>
      </aside>
    </>
  );
};
