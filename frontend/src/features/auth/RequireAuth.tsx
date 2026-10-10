import { Navigate, Outlet, useLocation } from "react-router";
import { ErrorState, Spinner } from "@/components/States";
import { useMe } from "./hooks";

export function RequireAuth() {
  const { data: me, isPending, error, refetch } = useMe();
  const location = useLocation();

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
  return <Outlet />;
}
