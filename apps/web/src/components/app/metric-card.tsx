import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  note,
  detail,
  tone = "default",
  className,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  detail?: ReactNode;
  tone?: "default" | "positive" | "negative" | "warning";
  className?: string;
}) {
  return (
    <Card className={cn("min-w-0 shadow-none", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          className={cn(
            "metric-value truncate text-xl font-semibold",
            tone === "positive" && "text-positive",
            tone === "negative" && "text-negative",
            tone === "warning" && "text-warning",
          )}
          title={typeof value === "string" ? value : undefined}
        >
          {value}
        </div>
        {note && (
          <p className="mt-1 min-h-8 text-xs leading-4 text-muted-foreground">
            {note}
          </p>
        )}
        {detail && <div className="mt-3 border-t pt-3 text-xs">{detail}</div>}
      </CardContent>
    </Card>
  );
}
