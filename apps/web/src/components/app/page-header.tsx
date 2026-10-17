import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  eyebrow,
  badge,
  demo,
  actions,
  context,
  className,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  badge?: ReactNode;
  demo?: boolean;
  actions?: ReactNode;
  context?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "mb-7 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground">
            {eyebrow}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {title}
          </h1>
          {demo && <Badge variant="secondary">Demo data</Badge>}
          {badge}
        </div>
        {description && (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        )}
        {context && <div className="mt-3 flex flex-wrap gap-2">{context}</div>}
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
          {actions}
        </div>
      )}
    </header>
  );
}
