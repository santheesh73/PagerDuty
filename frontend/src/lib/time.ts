/** Timezone maths with Intl only — enough for laying out days in a schedule's zone. */

function partsIn(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(date);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return {
    y: get("year"),
    m: get("month"),
    d: get("day"),
    h: get("hour"),
    min: get("minute"),
    s: get("second"),
  };
}

/** Milliseconds `timeZone` is ahead of UTC at instant `t`. */
export function zoneOffset(t: number, timeZone: string): number {
  const p = partsIn(new Date(t), timeZone);
  const asUtc = Date.UTC(p.y, p.m - 1, p.d, p.h, p.min, p.s);
  return asUtc - Math.floor(t / 1000) * 1000;
}

/** The instant local midnight starts on the calendar day containing `date` in `timeZone`. */
export function startOfDayIn(date: Date, timeZone: string): Date {
  const p = partsIn(date, timeZone);
  const guess = Date.UTC(p.y, p.m - 1, p.d);
  // Two passes settle the offset even when midnight is near a DST transition.
  let t = guess - zoneOffset(guess, timeZone);
  t = guess - zoneOffset(t, timeZone);
  return new Date(t);
}

/** Local midnights for `days` consecutive days (plus the end), DST-aware: days can be 23/25h. */
export function dayStartsIn(from: Date, days: number, timeZone: string): Date[] {
  const starts = [startOfDayIn(from, timeZone)];
  for (let i = 0; i < days; i++) {
    const previous = starts[starts.length - 1]!;
    starts.push(startOfDayIn(new Date(previous.getTime() + 26 * 3_600_000), timeZone));
  }
  return starts;
}
