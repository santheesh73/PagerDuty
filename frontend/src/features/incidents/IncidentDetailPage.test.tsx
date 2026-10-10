import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { incidentFixture } from "@/test/fixtures";
import { json, mockFetch, renderRoute } from "@/test/utils";
import { IncidentDetailPage } from "./IncidentDetailPage";

const DETAIL = "GET /api/v1/incidents/7/";
const TIMELINE = "GET /api/v1/incidents/7/timeline/";
const EMPTY_PAGE = { next: null, previous: null, results: [] };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

function renderIncident() {
  return renderRoute(<IncidentDetailPage />, { path: "/incidents/:id", url: "/incidents/7" });
}

const statusBadge = () =>
  within(screen.getByRole("heading", { level: 1 }).parentElement!).getAllByText(
    /Triggered|Acknowledged|Resolved/,
  )[0]!;

beforeEach(() => {
  document.cookie = "csrftoken=test-token";
});
afterEach(() => vi.unstubAllGlobals());

describe("IncidentDetailPage", () => {
  it("offers only the actions the incident's status allows", async () => {
    mockFetch({ [DETAIL]: () => incidentFixture(), [TIMELINE]: () => EMPTY_PAGE });
    renderIncident();

    const actions = await screen.findByRole("group", { name: "Incident actions" });
    const labels = within(actions)
      .getAllByRole("button")
      .map((b) => b.textContent?.replace(/[A-Z]$/, "").trim());
    expect(labels).toEqual(["Acknowledge", "Resolve", "Escalate", "Reassign"]);
    expect(screen.queryByRole("button", { name: /Unacknowledge/ })).not.toBeInTheDocument();
  });

  it("acknowledges optimistically before the server answers", async () => {
    const server = deferred<Response>();
    mockFetch({
      [DETAIL]: () => incidentFixture(),
      [TIMELINE]: () => EMPTY_PAGE,
      "POST /api/v1/incidents/7/acknowledge/": () => server.promise,
    });
    renderIncident();
    await userEvent.click(await screen.findByRole("button", { name: /Acknowledge/ }));

    // The request is still in flight, but the UI already reflects the new state.
    await waitFor(() => expect(statusBadge()).toHaveTextContent("Acknowledged"));
    expect(screen.getByRole("button", { name: /Unacknowledge/ })).toBeInTheDocument();

    server.resolve(
      json(
        incidentFixture({
          status: "acknowledged",
          allowed_actions: ["unacknowledge", "resolve", "reassign", "escalate", "add_note"],
        }),
      ),
    );
    expect(await screen.findByText("Acknowledged #1042")).toBeInTheDocument();
  });

  it("rolls the optimistic update back when the server refuses", async () => {
    mockFetch({
      [DETAIL]: () => incidentFixture(),
      [TIMELINE]: () => EMPTY_PAGE,
      "POST /api/v1/incidents/7/acknowledge/": () =>
        json(
          {
            error: {
              code: "invalid_transition",
              message: "Someone else just resolved it.",
              details: {},
            },
          },
          409,
        ),
    });
    renderIncident();
    await userEvent.click(await screen.findByRole("button", { name: /Acknowledge/ }));

    expect(await screen.findByText("Couldn't acknowledge the incident")).toBeInTheDocument();
    expect(screen.getByText("Someone else just resolved it.")).toBeInTheDocument();
    await waitFor(() => expect(statusBadge()).toHaveTextContent("Triggered"));
    expect(screen.getByRole("button", { name: /^Acknowledge/ })).toBeInTheDocument();
  });

  it("supports keyboard shortcuts for allowed actions", async () => {
    const ack = vi.fn(() => incidentFixture({ status: "acknowledged", allowed_actions: [] }));
    mockFetch({
      [DETAIL]: () => incidentFixture(),
      [TIMELINE]: () => EMPTY_PAGE,
      "POST /api/v1/incidents/7/acknowledge/": ack,
    });
    renderIncident();
    await screen.findByRole("button", { name: /Acknowledge/ });

    await userEvent.keyboard("a");
    await waitFor(() => expect(ack).toHaveBeenCalledTimes(1));
  });

  it("hides every action from viewers", async () => {
    mockFetch({
      [DETAIL]: () => incidentFixture({ allowed_actions: [] }),
      [TIMELINE]: () => EMPTY_PAGE,
    });
    renderIncident();
    await screen.findByRole("heading", { name: "Disk 95% full on db-1" });
    expect(screen.queryByRole("group", { name: "Incident actions" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Add a note")).not.toBeInTheDocument();
  });

  it("shows the frozen escalation path with the current level", async () => {
    mockFetch({ [DETAIL]: () => incidentFixture(), [TIMELINE]: () => EMPTY_PAGE });
    renderIncident();
    const current = await screen.findByText(/Level 1 · current/);
    expect(current.closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Ada Okafor")).toBeInTheDocument();
    expect(screen.getByText(/Escalates to the next level in/)).toBeInTheDocument();
  });
});
