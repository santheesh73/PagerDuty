import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockFetch, renderRoute } from "@/test/utils";
import { LoginPage } from "./LoginPage";

const me = {
  id: 1,
  email: "ada@example.com",
  name: "Ada",
  timezone: "UTC",
  is_staff: false,
  memberships: [],
};

afterEach(() => vi.unstubAllGlobals());

describe("sign-in with two-factor authentication", () => {
  it("asks for a code after the password and signs in only once the code is accepted", async () => {
    document.cookie = "csrftoken=t";
    const codes: string[] = [];
    mockFetch({
      "GET /api/v1/me/": () => new Response("{}", { status: 403 }),
      "POST /api/v1/auth/login/": () => ({ mfa_required: true }),
      "POST /api/v1/auth/mfa/": (_url, init) => {
        const { code } = JSON.parse(String(init.body)) as { code: string };
        codes.push(code);
        return code === "123456"
          ? me
          : new Response(
              JSON.stringify({
                error: { code: "invalid_code", message: "That code is not right.", details: {} },
              }),
              { status: 401 },
            );
      },
    });
    renderRoute(<LoginPage />, { path: "/login", url: "/login" });
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    const code = await screen.findByLabelText("Authentication code");
    await user.type(code, "000000");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText("That code is not right.")).toBeInTheDocument();

    await user.clear(code);
    await user.type(code, "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(codes).toEqual(["000000", "123456"]));
  });

  it("offers a way back when the code step has expired", async () => {
    document.cookie = "csrftoken=t";
    mockFetch({
      "GET /api/v1/me/": () => new Response("{}", { status: 403 }),
      "POST /api/v1/auth/login/": () => ({ mfa_required: true }),
      "POST /api/v1/auth/mfa/": () =>
        new Response(
          JSON.stringify({
            error: { code: "mfa_session_expired", message: "Sign in again.", details: {} },
          }),
          { status: 401 },
        ),
    });
    renderRoute(<LoginPage />, { path: "/login", url: "/login" });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "pw-pw-pw-pw-pw");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await user.type(await screen.findByLabelText("Authentication code"), "111111");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    await user.click(await screen.findByRole("button", { name: "Sign in again" }));
    expect(await screen.findByLabelText("Password")).toHaveValue("");
  });

  it("links to password reset", async () => {
    mockFetch({ "GET /api/v1/me/": () => new Response("{}", { status: 403 }) });
    renderRoute(<LoginPage />, { path: "/login", url: "/login" });
    expect(await screen.findByRole("link", { name: "Forgot your password?" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });
});
