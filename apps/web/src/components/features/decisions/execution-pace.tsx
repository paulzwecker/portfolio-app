import { Check, CircleAlert, CircleHelp, Clock3, X } from "lucide-react";
import { statusLabel } from "@/lib/display";
import { cn } from "@/lib/utils";

// Keep the generated feature copy compatible while canonical decision components
// remain at their existing source path during the incremental shell migration.
export { ExecutionPaceCompact } from "@/components/execution-pace";

export type StatusTone =
  "positive" | "negative" | "warning" | "info" | "neutral";

const toneClasses: Record<StatusTone, string> = {
  positive: "border-positive/35 bg-positive/10 text-positive",
  negative: "border-negative/35 bg-negative/10 text-negative",
  warning: "border-warning/35 bg-warning/10 text-warning",
  info: "border-info/35 bg-info/10 text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

const toneIcons = {
  positive: Check,
  negative: X,
  warning: CircleAlert,
  info: Clock3,
  neutral: CircleHelp,
} satisfies Record<StatusTone, typeof Check>;

export function statusTone(value: string | null | undefined): StatusTone {
  const normalized = value?.trim().toUpperCase().replaceAll("-", "_");
  if (
    normalized &&
    [
      "AVAILABLE",
      "FRESH",
      "COMPLETE",
      "PASS",
      "SUCCEEDED",
      "ACCEPTED",
      "PUBLISHED",
      "ASSESSED",
    ].includes(normalized)
  )
    return "positive";
  if (
    normalized &&
    [
      "FAILED",
      "ERROR",
      "UNAVAILABLE",
      "INVALID",
      "REJECTED",
      "CONFLICT",
    ].includes(normalized)
  )
    return "negative";
  if (
    normalized &&
    [
      "STALE",
      "PARTIAL",
      "REVIEW",
      "DATA_CHECK",
      "PENDING",
      "BLOCKED",
      "REFRESHING",
      "IN_PROGRESS",
    ].includes(normalized)
  )
    return "warning";
  if (normalized && ["INFO", "RUNNING", "QUEUED"].includes(normalized))
    return "info";
  return "neutral";
}

export function StatusIndicator({
  label,
  tone,
  status,
  className,
}: {
  label?: string;
  tone?: StatusTone;
  status?: string | null;
  className?: string;
}) {
  const resolvedTone = tone ?? statusTone(status);
  const Icon = toneIcons[resolvedTone];
  const text = label ?? statusLabel(status);

  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        toneClasses[resolvedTone],
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      <span>{text}</span>
    </span>
  );
}
