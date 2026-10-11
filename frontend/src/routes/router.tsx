import type { ComponentType } from "react";
import { createBrowserRouter, type RouteObject } from "react-router";
import { AppShell } from "@/components/AppShell";
import { NotFound } from "@/components/NotFound";
import { RouteError } from "@/components/RouteError";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { IncidentDetailPage } from "@/features/incidents/IncidentDetailPage";
import { IncidentListPage } from "@/features/incidents/IncidentListPage";

/**
 * The pages a responder opens first (sign-in, dashboard, incidents) ship in the main bundle; the
 * rest load on demand, so the 3 a.m. page-to-acknowledge path stays small (budget enforced in CI by
 * scripts/check-bundle.mjs).
 */
function page<M>(load: () => Promise<M>, pick: (module: M) => ComponentType): RouteObject["lazy"] {
  return async () => ({ Component: pick(await load()) });
}

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage />, errorElement: <RouteError /> },
  {
    path: "/forgot-password",
    lazy: page(
      () => import("@/features/auth/PasswordResetPages"),
      (m) => m.ForgotPasswordPage,
    ),
    errorElement: <RouteError />,
  },
  {
    path: "/reset-password",
    lazy: page(
      () => import("@/features/auth/PasswordResetPages"),
      (m) => m.ResetPasswordPage,
    ),
    errorElement: <RouteError />,
  },
  {
    element: <RequireAuth />,
    errorElement: <RouteError />,
    children: [
      {
        element: <AppShell />,
        errorElement: <RouteError />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "incidents", element: <IncidentListPage /> },
          { path: "incidents/:id", element: <IncidentDetailPage /> },
          {
            path: "services",
            lazy: page(
              () => import("@/features/services/ServicesPage"),
              (m) => m.ServicesPage,
            ),
          },
          {
            path: "services/:id",
            lazy: page(
              () => import("@/features/services/ServiceDetailPage"),
              (m) => m.ServiceDetailPage,
            ),
          },
          {
            path: "escalation-policies",
            lazy: page(
              () => import("@/features/policies/PoliciesPage"),
              (m) => m.PoliciesPage,
            ),
          },
          {
            path: "escalation-policies/:id",
            lazy: page(
              () => import("@/features/policies/PolicyPage"),
              (m) => m.PolicyPage,
            ),
          },
          {
            path: "schedules",
            lazy: page(
              () => import("@/features/schedules/SchedulesPage"),
              (m) => m.SchedulesPage,
            ),
          },
          {
            path: "schedules/:id",
            lazy: page(
              () => import("@/features/schedules/SchedulePage"),
              (m) => m.SchedulePage,
            ),
          },
          {
            path: "analytics",
            lazy: page(
              () => import("@/features/analytics/AnalyticsPage"),
              (m) => m.AnalyticsPage,
            ),
          },
          {
            path: "notifications",
            lazy: page(
              () => import("@/features/notifications/InboxPage"),
              (m) => m.InboxPage,
            ),
          },
          {
            path: "settings/security",
            lazy: page(
              () => import("@/features/security/SecurityPage"),
              (m) => m.SecurityPage,
            ),
          },
          {
            path: "audit-log",
            lazy: page(
              () => import("@/features/security/AuditLogPage"),
              (m) => m.AuditLogPage,
            ),
          },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
