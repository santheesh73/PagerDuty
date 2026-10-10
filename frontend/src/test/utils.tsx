import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { Toaster } from "sonner";
import { vi } from "vitest";

type Handler = (url: string, init: RequestInit) => unknown | Promise<unknown>;

export function json(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Route fetch calls by "METHOD path" (path without query string). Unmatched calls fail loudly. */
export function mockFetch(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = (init.method ?? "GET").toUpperCase();
    const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0]!;
    const handler = routes[`${method} ${path}`];
    if (!handler) throw new Error(`Unexpected fetch: ${method} ${path}`);
    const result = await handler(url, init);
    return result instanceof Response ? result : json(result);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function renderRoute(element: ReactElement, { path = "/", url = "/" } = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter([{ path, element }], { initialEntries: [url] });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
        <Toaster />
      </QueryClientProvider>,
    ),
  };
}
