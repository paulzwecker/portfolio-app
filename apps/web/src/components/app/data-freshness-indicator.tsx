import {
  StatusIndicator,
  type StatusTone,
} from "@/components/app/status-indicator";
import { dateTime, marketDate } from "@/lib/display";

const freshnessTone: Record<string, StatusTone> = {
  AVAILABLE: "positive",
  FRESH: "positive",
  STALE: "warning",
  PARTIAL: "warning",
  REFRESHING: "info",
  UNAVAILABLE: "neutral",
  UNKNOWN: "neutral",
};

export function DataFreshnessIndicator({
  state,
  observedAt,
  source,
  detail,
  timeLabel = "Observed",
  timeKind = "timestamp",
}: {
  state: string;
  observedAt?: string | null;
  source?: string | null;
  detail?: string | null;
  timeLabel?: string;
  timeKind?: "timestamp" | "market-date";
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      <StatusIndicator
        status={state}
        tone={freshnessTone[state] ?? "neutral"}
      />
      {source && <span className="text-muted-foreground">{source}</span>}
      {observedAt && (
        <time dateTime={observedAt} className="text-muted-foreground">
          {timeLabel}{" "}
          {timeKind === "market-date"
            ? marketDate(observedAt)
            : dateTime(observedAt)}
        </time>
      )}
      {detail && <span className="text-muted-foreground">{detail}</span>}
    </div>
  );
}
