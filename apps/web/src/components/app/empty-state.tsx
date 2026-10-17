import type { ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingSkeleton } from "@/components/app/loading-skeleton";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  actions,
  icon,
  className,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed bg-muted/30 px-5 py-6",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-muted-foreground">
          {icon ?? <AlertTriangle aria-hidden="true" className="size-4" />}
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{title}</h3>
          {description && (
            <p className="mt-1 text-sm leading-5 text-muted-foreground">
              {description}
            </p>
          )}
          {actions && (
            <div className="mt-4 flex flex-wrap gap-2">{actions}</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function PendingOrError({
  error,
  retry,
}: {
  error?: string;
  retry: () => void;
}) {
  return error ? (
    <div role="alert" className="rounded-xl border bg-card p-6">
      <p>{error}</p>
      <Button className="mt-4" variant="outline" onClick={retry}>
        <RefreshCw aria-hidden="true" />
        Retry
      </Button>
    </div>
  ) : (
    <div role="status" aria-live="polite" className="py-6">
      <span className="sr-only">Loading research data</span>
      <LoadingSkeleton lines={2} label="Loading research data" />
    </div>
  );
}
