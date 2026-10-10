import { describe, expect, it } from "vitest";
import { formatDuration, formatRelative } from "./format";
import { dayStartsIn, startOfDayIn } from "./time";

describe("formatDuration", () => {
  it.each([
    [null, "—"],
    [42, "42s"],
    [60, "1m"],
    [546, "9m 06s"],
    [3_660, "1h 01m"],
    [90_000, "1d 1h"],
  ])("%s seconds → %s", (seconds, expected) => {
    expect(formatDuration(seconds)).toBe(expected);
  });
});

describe("formatRelative", () => {
  it("says just now for very recent times", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(formatRelative("2026-01-01T11:59:50Z", now)).toBe("just now");
    expect(formatRelative("2026-01-01T11:00:00Z", now)).toBe("1 hr. ago");
  });
});

describe("schedule-zone days", () => {
  it("finds local midnight in the schedule's zone, not the browser's", () => {
    const start = startOfDayIn(new Date("2026-03-07T15:00:00Z"), "America/New_York");
    expect(start.toISOString()).toBe("2026-03-07T05:00:00.000Z");
  });

  it("makes DST days 23 and 25 hours long", () => {
    const spring = dayStartsIn(new Date("2026-03-08T12:00:00Z"), 1, "America/New_York");
    expect((spring[1]!.getTime() - spring[0]!.getTime()) / 3_600_000).toBe(23);
    const fall = dayStartsIn(new Date("2026-11-01T12:00:00Z"), 1, "America/New_York");
    expect((fall[1]!.getTime() - fall[0]!.getTime()) / 3_600_000).toBe(25);
  });
});
