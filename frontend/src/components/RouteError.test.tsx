import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RouteError } from "./RouteError";

function Boom(): never {
  throw new Error("render exploded: secret internals");
}

function renderAt(url: string) {
  const router = createMemoryRouter(
    [
      { path: "/", element: <p>Dashboard</p>, errorElement: <RouteError /> },
      { path: "/broken", element: <Boom />, errorElement: <RouteError /> },
    ],
    { initialEntries: [url] },
  );
  return render(<RouterProvider router={router} />);
}

afterEach(() => vi.restoreAllMocks());

describe("route error boundary", () => {
  it("shows a recoverable error page instead of a blank screen when a page throws", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderAt("/broken");
    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the dashboard" })).toHaveAttribute("href", "/");
    // The error's message is for Sentry and the console, not the screen.
    expect(screen.queryByText(/secret internals/)).not.toBeInTheDocument();
  });

  it("says 'not found' for an unknown URL", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    renderAt("/no-such-page");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
