import { describe, expect, it } from "vitest";
import { beforeSend, scrub } from "./sentry";

describe("error reporting scrubber", () => {
  it("redacts secret-looking keys at any depth and keeps the rest", () => {
    const cleaned = scrub({ a: { password: "hunter2", note: "ok" }, list: [{ api_key: "K" }] });
    expect(JSON.stringify(cleaned)).not.toMatch(/hunter2|"K"/);
    expect(cleaned.a.note).toBe("ok");
  });

  it("drops cookies, headers, bodies and the user before sending", () => {
    const event = beforeSend({
      request: {
        cookies: { sessionid: "S" },
        headers: { Cookie: "S" },
        data: { routing_key: "R" },
        url: "/x",
      },
      user: { email: "a@b.c" },
      message: "boom",
    });
    expect(event.request).toEqual({ url: "/x" });
    expect(event.user).toBeUndefined();
    expect(event.message).toBe("boom");
  });
});
