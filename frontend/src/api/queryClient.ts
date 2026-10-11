import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError } from "./client";
import { keys } from "./keys";

/**
 * A 401/403 that says "not authenticated" mid-session means the session ended (expired, revoked
 * from another device, password reset). Drop the cached user so RequireAuth sends the person to
 * sign in and back, instead of leaving every page showing an error.
 */
function handleAuthError(client: QueryClient, error: unknown) {
  if (!(error instanceof ApiError)) return;
  const signedOut =
    error.status === 401 ||
    (error.status === 403 && ["not_authenticated", "authentication_failed"].includes(error.code));
  if (signedOut && client.getQueryData(keys.me)) {
    client.setQueryData(keys.me, null);
    toast("Your session has ended. Sign in again to continue.");
  }
  if (error.code === "mfa_enrollment_required") {
    void client.invalidateQueries({ queryKey: ["me", "mfa"] });
  }
}

export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (error) => handleAuthError(client, error) }),
    mutationCache: new MutationCache({ onError: (error) => handleAuthError(client, error) }),
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: true,
        // Don't retry client errors (403/404/422): they won't fix themselves.
        retry: (count, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      },
    },
  });
  return client;
}
