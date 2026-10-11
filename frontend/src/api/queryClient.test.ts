import { afterEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { ApiError } from "./client";
import { keys } from "./keys";
import { createQueryClient } from "./queryClient";

vi.mock("sonner", () => ({ toast: vi.fn() }));

afterEach(() => vi.clearAllMocks());

async function failQuery(client: ReturnType<typeof createQueryClient>, error: ApiError) {
  await client
    .fetchQuery({ queryKey: ["incidents"], queryFn: () => Promise.reject(error), retry: false })
    .catch(() => undefined);
}

describe("session expiry", () => {
  it("signs the person out once when a request comes back 401 mid-session", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.me, { id: 1, email: "ada@example.com" });

    await failQuery(client, new ApiError(401, "not_authenticated", "Sign in."));
    await failQuery(client, new ApiError(401, "not_authenticated", "Sign in."));

    expect(client.getQueryData(keys.me)).toBeNull();
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith("Your session has ended. Sign in again to continue.");
  });

  it("treats DRF's 403 not_authenticated as an ended session too", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.me, { id: 1 });
    await failQuery(client, new ApiError(403, "not_authenticated", "Sign in."));
    expect(client.getQueryData(keys.me)).toBeNull();
  });

  it("does not sign anyone out on an ordinary permission error", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.me, { id: 1 });
    await failQuery(client, new ApiError(403, "permission_denied", "Not on this team."));
    expect(client.getQueryData(keys.me)).toEqual({ id: 1 });
    expect(toast).not.toHaveBeenCalled();
  });

  it("reacts to failed mutations as well as queries", async () => {
    const client = createQueryClient();
    client.setQueryData(keys.me, { id: 1 });
    const mutation = client.getMutationCache().build(client, {
      mutationFn: () => Promise.reject(new ApiError(401, "not_authenticated", "Sign in.")),
    });
    await mutation.execute(undefined).catch(() => undefined);
    expect(client.getQueryData(keys.me)).toBeNull();
  });

  it("refreshes the MFA status when the server says enrolment is required", async () => {
    const client = createQueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    await failQuery(client, new ApiError(403, "mfa_enrollment_required", "Set up 2FA."));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me", "mfa"] });
  });
});
