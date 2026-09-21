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
} from 'lucide-react';
import { cn } from '../../lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
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

export const Sidebar: React.FC = () => {
  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col shrink-0 min-h-screen">
      {/* Brand Header */}
      <div className="h-16 flex items-center gap-3 px-6 border-b border-slate-800">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm">
          <Flame className="w-5 h-5" aria-hidden="true" />
        </div>
        <div>
          <span className="font-bold text-sm tracking-tight text-white block">IncidentPlatform</span>
          <span className="text-[10px] text-slate-400 font-mono block uppercase">Core Workbench</span>
        </div>
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
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
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

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800/80 text-[11px] text-slate-500 space-y-1">
        <div className="flex items-center justify-between text-slate-400">
          <span>Phase 6</span>
          <span className="text-emerald-400 font-mono">Ready</span>
        </div>
        <div className="truncate">React 18 • Django 5 • PG • Celery</div>
      </div>
    </aside>
  );
};
