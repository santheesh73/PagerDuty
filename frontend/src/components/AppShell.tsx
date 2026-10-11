import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router";
import {
  BarChart3,
  Bell,
  Boxes,
  CalendarClock,
  LayoutDashboard,
  LogOut,
  ScrollText,
  ShieldCheck,
  Monitor,
  Moon,
  Siren,
  Sun,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useTheme, type ThemePreference } from "@/lib/theme";
import { useLogout, useMe } from "@/features/auth/hooks";
import { useUnreadCount } from "@/features/notifications/hooks";
import { Avatar } from "./Avatar";
import { Logo } from "./Logo";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/incidents", label: "Incidents", icon: Siren },
  { to: "/services", label: "Services", icon: Boxes },
  { to: "/escalation-policies", label: "Escalation policies", icon: Workflow },
  { to: "/schedules", label: "Schedules", icon: CalendarClock },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

export function AppShell() {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-col">
        <TopBar />
        <main id="main" className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="hidden border-r border-border bg-surface lg:block">
      <div className="sticky top-0 flex h-screen flex-col">
        <Link to="/" className="flex items-center gap-2.5 px-5 py-5">
          <Logo />
          <span className="text-base font-semibold tracking-tight">Pulse</span>
        </Link>
        <nav aria-label="Primary" className="flex-1 space-y-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent-soft text-accent"
                    : "text-muted hover:bg-surface-2 hover:text-text",
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <p className="px-5 py-4 text-xs text-subtle">v1.0 · Postgres is the source of truth</p>
      </div>
    </aside>
  );
}

function TopBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1280px] items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2 lg:hidden" aria-label="Pulse home">
          <Logo className="size-6" />
        </Link>
        <nav aria-label="Primary" className="-mx-1 flex flex-1 gap-1 overflow-x-auto lg:hidden">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={label}
              className={({ isActive }) =>
                cn(
                  "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium whitespace-nowrap",
                  isActive ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="size-4" aria-hidden />
                  {/* Icons only below desktop; the current page keeps its label for context. */}
                  <span className={isActive ? "hidden sm:inline" : "sr-only"}>{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <NotificationBell />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

function NotificationBell() {
  const { data } = useUnreadCount();
  const count = data?.count ?? 0;
  return (
    <Link
      to="/notifications"
      className="relative rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-text"
      aria-label={count ? `Notifications, ${count} unread` : "Notifications"}
    >
      <Bell className="size-5" aria-hidden />
      {count > 0 && (
        <span className="tabular absolute -top-0.5 -right-0.5 min-w-4.5 rounded-full bg-critical-solid px-1 text-center text-[10px] leading-4.5 font-semibold text-on-solid">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}

function UserMenu() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const [theme, setTheme] = useTheme();
  const [open, setOpen] = useState(false);
  if (!me) return null;

  return (
    <div
      className="relative"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="flex items-center gap-2 rounded-lg p-1 pr-2 hover:bg-surface-2"
      >
        <Avatar user={me} />
        <span className="hidden text-sm font-medium md:inline">{me.name}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-64 rounded-xl border border-border bg-surface p-1.5 shadow-pop"
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        >
          <div className="px-2.5 py-2">
            <p className="font-medium">{me.name}</p>
            <p className="truncate text-xs text-muted">{me.email}</p>
            <p className="mt-1 text-xs text-subtle">
              {me.memberships.map((m) => `${m.team.name} (${m.role})`).join(" · ") || "No teams"}
            </p>
          </div>
          <div className="my-1 border-t border-border" />
          <div className="px-2.5 py-1.5 text-xs font-medium text-muted">Theme</div>
          <div className="grid grid-cols-3 gap-1 px-1.5 pb-1.5" role="group" aria-label="Theme">
            {THEMES.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                role="menuitemradio"
                aria-checked={theme === value}
                onClick={() => setTheme(value)}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-lg py-2 text-xs",
                  theme === value ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </button>
            ))}
          </div>
          <div className="my-1 border-t border-border" />
          <Link
            to="/settings/security"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-text"
          >
            <ShieldCheck className="size-4" aria-hidden /> Security
          </Link>
          {(me.is_staff || me.memberships.some((m) => m.role === "admin")) && (
            <Link
              to="/audit-log"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-text"
            >
              <ScrollText className="size-4" aria-hidden /> Audit log
            </Link>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-text"
          >
            <LogOut className="size-4" aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
