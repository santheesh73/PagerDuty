import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, buildUrl } from "./client";
import { json, mockFetch } from "@/test/utils";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("api client", () => {
  it("maps the error envelope to a typed ApiError", async () => {
    mockFetch({
      "POST /api/v1/incidents/1/acknowledge/": () =>
        json(
          {
            error: {
              code: "invalid_transition",
              message: "Already acknowledged.",
              details: { allowed: ["resolve"] },
            },
          },
          409,
        ),
    });
    document.cookie = "csrftoken=abc";
    const error = await api("/incidents/1/acknowledge/", { method: "POST" }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: "invalid_transition",
      message: "Already acknowledged.",
    });
    expect((error as ApiError).details).toEqual({ allowed: ["resolve"] });
  });

  it("sends the CSRF token on unsafe methods, fetching the cookie first if needed", async () => {
    const fetchMock = mockFetch({
      "GET /api/v1/auth/csrf/": () => {
        document.cookie = "csrftoken=fresh-token";
        return json(null, 204);
      },
      "POST /api/v1/notifications/read-all/": () => ({ count: 2 }),
    });
    await expect(api("/notifications/read-all/", { method: "POST" })).resolves.toEqual({
      count: 2,
    });
    const [, init] = fetchMock.mock.calls[1]!;
    expect((init!.headers as Record<string, string>)["X-CSRFToken"]).toBe("fresh-token");
    expect(init!.credentials).toBe("same-origin");
  });

  it("does not send a CSRF header on GET", async () => {
    const fetchMock = mockFetch({ "GET /api/v1/me/": () => ({ id: 1 }) });
    await api("/me/");
    const [, init] = fetchMock.mock.calls[0]!;
    expect((init!.headers as Record<string, string>)["X-CSRFToken"]).toBeUndefined();
  });

  it("turns network failures into a friendly ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api("/me/")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });

  it("builds query strings without empty values", () => {
    expect(
      buildUrl("/incidents/", {
        status: "triggered",
        service: "",
        urgency: undefined,
        page_size: 25,
      }),
    ).toBe("/api/v1/incidents/?status=triggered&page_size=25");
    expect(buildUrl("/api/v1/incidents/?cursor=abc")).toBe("/api/v1/incidents/?cursor=abc");
  });

  it("keeps pagination links on this origin even if the backend names another host", () => {
    expect(buildUrl("https://pulse-api.internal:8000/api/v1/incidents/?cursor=abc")).toBe(
      "/api/v1/incidents/?cursor=abc",
    );
  });
});
