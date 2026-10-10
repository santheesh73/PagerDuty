import { cn } from "@/lib/cn";
import { PERSON_COLORS } from "@/lib/colors";
import { colorSlot, initials } from "@/lib/format";

export function Avatar({
  user,
  size = "md",
  className,
}: {
  user: { id: number; name: string };
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <span
      title={user.name}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        size === "sm" ? "size-6 text-[10px]" : "size-8 text-xs",
        PERSON_COLORS[colorSlot(user.id, PERSON_COLORS.length)],
        className,
      )}
      aria-hidden
    >
      {initials(user.name)}
    </span>
  );
}

export function Person({
  user,
  muted,
}: {
  user?: { id: number; name: string } | null;
  muted?: string;
}) {
  if (!user) return <span className="text-subtle">{muted ?? "Unassigned"}</span>;
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <Avatar user={user} size="sm" />
      <span className="truncate">{user.name}</span>
    </span>
  );
}
