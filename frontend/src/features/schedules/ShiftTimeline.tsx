import type { Shift } from "@/api/types";
import { PERSON_COLORS } from "@/lib/colors";
import { cn } from "@/lib/cn";
import { colorSlot, formatDateTime } from "@/lib/format";

/**
 * A horizontal on-call timeline. `dayStarts` are local midnights in the schedule's zone
 * (days.length + 1 instants), so a DST day really is drawn 23 or 25 hours wide, and shift
 * positions come straight from the backend's render_shifts.
 */
export function ShiftTimeline({
  shifts,
  dayStarts,
  timeZone,
  now,
}: {
  shifts: Shift[];
  dayStarts: Date[];
  timeZone: string;
  now: number;
}) {
  const start = dayStarts[0]!.getTime();
  const end = dayStarts[dayStarts.length - 1]!.getTime();
  const span = end - start;
  const pct = (t: number) => Math.min(100, Math.max(0, ((t - start) / span) * 100));
  const days = dayStarts.slice(0, -1);
  const columns = days.map((d, i) => `${dayStarts[i + 1]!.getTime() - d.getTime()}fr`).join(" ");
  const dayLabel = new Intl.DateTimeFormat("en", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone,
  });
  const hhmm = new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  });
  const nowPct = now >= start && now < end ? pct(now) : null;

  return (
    <div className="overflow-x-auto" data-testid="shift-timeline">
      <div className="relative min-w-[680px]">
        <div
          className="grid border-b border-border text-xs text-muted"
          style={{ gridTemplateColumns: columns }}
        >
          {days.map((day) => (
            <div
              key={day.toISOString()}
              className="border-l border-border px-2 py-2 first:border-l-0"
            >
              {dayLabel.format(day)}
            </div>
          ))}
        </div>
        <div className="relative h-[72px]">
          <div
            className="absolute inset-0 grid"
            style={{ gridTemplateColumns: columns }}
            aria-hidden
          >
            {days.map((day) => (
              <div key={day.toISOString()} className="border-l border-border first:border-l-0" />
            ))}
          </div>
          <ul aria-label="On-call shifts">
            {shifts.map((shift) => {
              const left = pct(new Date(shift.start).getTime());
              const width = pct(new Date(shift.end).getTime()) - left;
              const override = shift.source === "override";
              const label = `${shift.user.name}${override ? " (override)" : ""}: ${formatDateTime(shift.start, timeZone)} → ${formatDateTime(shift.end, timeZone)}`;
              return (
                <li
                  key={`${shift.start}-${shift.user.id}`}
                  aria-label={label}
                  title={label}
                  className={cn(
                    "absolute top-3 bottom-3 overflow-hidden rounded-md px-2 py-1 text-xs leading-tight font-medium ring-1 ring-black/5 ring-inset",
                    PERSON_COLORS[colorSlot(shift.user.id, PERSON_COLORS.length)],
                    override && "ring-2 ring-current/50",
                  )}
                  style={{
                    left: `${left}%`,
                    width: `calc(${width}% - 2px)`,
                    backgroundImage: override
                      ? "repeating-linear-gradient(135deg, transparent 0 5px, rgb(0 0 0 / 0.07) 5px 10px)"
                      : undefined,
                  }}
                >
                  <span className="block truncate">{shift.user.name}</span>
                  <span className="block truncate font-normal">
                    {override
                      ? "override"
                      : `${hhmm.format(new Date(shift.start))} → ${hhmm.format(new Date(shift.end))}`}
                  </span>
                </li>
              );
            })}
          </ul>
          {nowPct !== null && (
            <div
              className="pointer-events-none absolute -top-1 bottom-0 w-0.5 bg-critical"
              style={{ left: `${nowPct}%` }}
              aria-hidden
            >
              <span className="absolute -top-0.5 -left-[3px] size-2 rounded-full bg-critical" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
