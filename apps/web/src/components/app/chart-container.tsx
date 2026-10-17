import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function ChartContainer({
  title,
  description,
  children,
  source,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  source?: ReactNode;
  className?: string;
}) {
  const generatedId = useId();
  const titleId = `chart-${generatedId.replaceAll(":", "")}`;
  return (
    <figure
      aria-labelledby={titleId}
      className={cn("min-w-0 rounded-xl border bg-card p-4 sm:p-5", className)}
    >
      <figcaption className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id={titleId} className="text-sm font-semibold">
            {title}
          </h3>
          {description && (
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {source && (
          <div className="text-xs text-muted-foreground">{source}</div>
        )}
      </figcaption>
      <div className="min-w-0 max-w-full">{children}</div>
    </figure>
  );
}
