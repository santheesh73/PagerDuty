import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { dayStartsIn } from "@/lib/time";
import { shift } from "@/test/fixtures";
import { ShiftTimeline } from "./ShiftTimeline";

const TZ = "America/New_York";

describe("ShiftTimeline", () => {
  it("lays shifts out proportionally across the week", () => {
    const dayStarts = dayStartsIn(new Date("2026-01-05T12:00:00Z"), 7, TZ); // Mon Jan 5, NY
    render(
      <ShiftTimeline
        timeZone={TZ}
        now={Date.parse("2026-01-01T00:00:00Z")}
        dayStarts={dayStarts}
        shifts={[
          shift(1, "Riley Chen", "2026-01-05T05:00:00Z", "2026-01-06T14:00:00Z"),
          shift(2, "Maya Patel", "2026-01-06T14:00:00Z", "2026-01-12T05:00:00Z"),
        ]}
      />,
    );

    const blocks = within(screen.getByRole("list", { name: "On-call shifts" })).getAllByRole(
      "listitem",
    );
    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toHaveStyle({ left: "0%" });
    // 33h of a 168h week ≈ 19.64%.
    expect(blocks[1]!.style.left).toMatch(/^19\.64/);
    expect(blocks[0]).toHaveTextContent("Riley Chen");
    expect(blocks[0]).toHaveTextContent("00:00 → 09:00");
  });

  it("labels days in the schedule's zone and widens the DST day", () => {
    const dayStarts = dayStartsIn(new Date("2026-10-31T16:00:00Z"), 2, TZ); // Sat Oct 31, Sun Nov 1 (25h)
    const { container } = render(
      <ShiftTimeline timeZone={TZ} now={0} dayStarts={dayStarts} shifts={[]} />,
    );
    expect(screen.getByText("Sat, Oct 31")).toBeInTheDocument();
    expect(screen.getByText("Sun, Nov 1")).toBeInTheDocument();
    const grid = container.querySelector("[style*='grid-template-columns']") as HTMLElement;
    expect(grid.style.gridTemplateColumns).toBe("86400000fr 90000000fr");
  });

  it("marks overrides", () => {
    const dayStarts = dayStartsIn(new Date("2026-01-05T12:00:00Z"), 1, TZ);
    render(
      <ShiftTimeline
        timeZone={TZ}
        now={0}
        dayStarts={dayStarts}
        shifts={[
          shift(3, "Jonas Berg", "2026-01-05T15:00:00Z", "2026-01-05T19:00:00Z", "override"),
        ]}
      />,
    );
    expect(screen.getByRole("listitem", { name: /Jonas Berg \(override\)/ })).toHaveTextContent(
      "override",
    );
  });
});
