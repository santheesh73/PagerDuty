import { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Schedule, TeamMember } from "@/api/types";
import { draftFrom, toPayload, validate, type Draft } from "./draft";
import { MAX_LEVELS } from "./hooks";
import { PolicyEditor } from "./PolicyEditor";

const members = [
  { user: { id: 1, name: "Ada Okafor", email: "a@x", timezone: "UTC" }, role: "admin" },
  { user: { id: 2, name: "Riley Chen", email: "r@x", timezone: "UTC" }, role: "responder" },
  { user: { id: 3, name: "Vic Ramos", email: "v@x", timezone: "UTC" }, role: "viewer" },
] as TeamMember[];
const schedules = [{ id: 9, name: "Payments primary", team: 1 }] as Schedule[];

function Harness({ initial, onDraft }: { initial: Draft; onDraft?: (d: Draft) => void }) {
  const [draft, setDraft] = useState(initial);
  return (
    <PolicyEditor
      draft={draft}
      onChange={(d) => {
        setDraft(d);
        onDraft?.(d);
      }}
      members={members}
      schedules={schedules}
    />
  );
}

describe("PolicyEditor", () => {
  it("builds levels with targets and delays into the API payload", async () => {
    let latest = draftFrom(undefined, 1);
    render(<Harness initial={latest} onDraft={(d) => (latest = d)} />);

    await userEvent.type(screen.getByLabelText("Policy name"), "Payments critical");
    await userEvent.selectOptions(
      screen.getByLabelText("Add someone to page at level 1"),
      "schedule:9",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add level" }));
    await userEvent.selectOptions(
      screen.getByLabelText("Add someone to page at level 2"),
      "user:1",
    );
    const delay = screen.getAllByRole("spinbutton")[1]!;
    await userEvent.clear(delay);
    await userEvent.type(delay, "15");

    expect(validate(latest)).toBeNull();
    expect(toPayload(latest)).toEqual({
      name: "Payments critical",
      team: 1,
      num_loops: 0,
      rules: [
        { delay_minutes: 5, targets: [{ type: "schedule", id: 9 }] },
        { delay_minutes: 15, targets: [{ type: "user", id: 1 }] },
      ],
    });
  });

  it("never offers viewers as targets", () => {
    render(<Harness initial={draftFrom(undefined, 1)} />);
    const picker = screen.getByLabelText("Add someone to page at level 1");
    expect(within(picker).queryByRole("option", { name: "Vic Ramos" })).not.toBeInTheDocument();
    expect(within(picker).getByRole("option", { name: "Riley Chen" })).toBeInTheDocument();
  });

  it("shows the level limit inline and stops at it", async () => {
    const full: Draft = {
      ...draftFrom(undefined, 1),
      levels: Array.from({ length: MAX_LEVELS }, (_, i) => ({
        key: i + 100,
        delay_minutes: 5,
        targets: [],
      })),
    };
    render(<Harness initial={full} />);
    expect(screen.getByRole("button", { name: "Add level" })).toBeDisabled();
    expect(screen.getByText(`${MAX_LEVELS} / ${MAX_LEVELS} levels`)).toBeInTheDocument();
  });

  it("reorders levels", async () => {
    let latest = draftFrom(undefined, 1);
    latest.levels = [
      { key: 1, delay_minutes: 5, targets: [{ type: "user", id: 1, name: "Ada Okafor" }] },
      { key: 2, delay_minutes: 10, targets: [{ type: "user", id: 2, name: "Riley Chen" }] },
    ];
    render(<Harness initial={latest} onDraft={(d) => (latest = d)} />);
    await userEvent.click(screen.getByRole("button", { name: "Move level 2 up" }));
    expect(latest.levels.map((l) => l.targets[0]!.name)).toEqual(["Riley Chen", "Ada Okafor"]);
  });

  it("explains what's missing before saving", () => {
    const draft = draftFrom(undefined, 1);
    expect(validate(draft)).toBe("Give the policy a name.");
    expect(validate({ ...draft, name: "x" })).toBe("Level 1 needs someone to page.");
  });
});
