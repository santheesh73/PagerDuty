import { createBrowserRouter } from "react-router";
import { AppShell } from "@/components/AppShell";
import { NotFound } from "@/components/NotFound";
import { LoginPage } from "@/features/auth/LoginPage";
import { ForgotPasswordPage, ResetPasswordPage } from "@/features/auth/PasswordResetPages";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { AnalyticsPage } from "@/features/analytics/AnalyticsPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { IncidentDetailPage } from "@/features/incidents/IncidentDetailPage";
import { IncidentListPage } from "@/features/incidents/IncidentListPage";
import { InboxPage } from "@/features/notifications/InboxPage";
import { PoliciesPage } from "@/features/policies/PoliciesPage";
import { PolicyPage } from "@/features/policies/PolicyPage";
import { SchedulePage } from "@/features/schedules/SchedulePage";
import { SchedulesPage } from "@/features/schedules/SchedulesPage";
import { ServiceDetailPage } from "@/features/services/ServiceDetailPage";
import { ServicesPage } from "@/features/services/ServicesPage";
import { AuditLogPage } from "@/features/security/AuditLogPage";
import { SecurityPage } from "@/features/security/SecurityPage";

export const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: "incidents", element: <IncidentListPage /> },
          { path: "incidents/:id", element: <IncidentDetailPage /> },
          { path: "services", element: <ServicesPage /> },
          { path: "services/:id", element: <ServiceDetailPage /> },
          { path: "escalation-policies", element: <PoliciesPage /> },
          { path: "escalation-policies/:id", element: <PolicyPage /> },
          { path: "schedules", element: <SchedulesPage /> },
          { path: "schedules/:id", element: <SchedulePage /> },
          { path: "analytics", element: <AnalyticsPage /> },
          { path: "notifications", element: <InboxPage /> },
          { path: "settings/security", element: <SecurityPage /> },
          { path: "audit-log", element: <AuditLogPage /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
