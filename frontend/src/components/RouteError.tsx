import { isRouteErrorResponse, Link, useRouteError } from "react-router";
import { useEffect } from "react";
import { Button } from "./Button";

/**
 * The router's error boundary: a render error anywhere below shows this instead of a blank page.
 * It is reported to Sentry when error reporting is configured (VITE_SENTRY_DSN).
 */
export function RouteError() {
  const error = useRouteError();
  const notFound = isRouteErrorResponse(error) && error.status === 404;

  useEffect(() => {
    if (notFound || !import.meta.env.VITE_SENTRY_DSN) return;
    void import("@sentry/react").then((Sentry) => Sentry.captureException(error));
  }, [error, notFound]);

  return (
    <main className="mx-auto mt-24 max-w-md px-4 text-center" role="alert">
      <h1 className="text-xl font-semibold">
        {notFound ? "Page not found" : "Something went wrong"}
      </h1>
      <p className="mt-2 text-muted">
        {notFound
          ? "That page doesn't exist."
          : "This page hit an unexpected error. Reloading usually fixes it; if not, it has been reported."}
      </p>
      <div className="mt-6 flex justify-center gap-2">
        <Button variant="primary" onClick={() => window.location.reload()}>
          Reload
        </Button>
        <Link
          to="/"
          className="inline-flex items-center rounded-lg px-3 text-sm text-accent hover:underline"
        >
          Go to the dashboard
        </Link>
      </div>
    </main>
  );
}
