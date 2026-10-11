import { Navigate, Outlet, useLocation } from "react-router";
import { ErrorState, Spinner } from "@/components/States";
import { useMe, useMfaStatus } from "./hooks";

export function RequireAuth() {
  const { data: me, isPending, error, refetch } = useMe();
  const location = useLocation();
  const mfa = useMfaStatus(Boolean(me));

  if (isPending) {
    return (
      <div className="grid min-h-screen place-items-center text-muted" role="status">
        <Spinner className="size-6" />
        <span className="sr-only">Loading Pulse</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="mx-auto mt-24 max-w-md px-4">
        <ErrorState error={error} onRetry={() => void refetch()} />
      </div>
    );
  }
  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  // Admins who must use MFA and have not enrolled can only reach the page that enrols them
  // (the API refuses everything else with mfa_enrollment_required).
  if (mfa.data?.enforced && !mfa.data.enabled && location.pathname !== "/settings/security") {
    return <Navigate to="/settings/security" replace />;
  }
  return <Outlet />;
}
