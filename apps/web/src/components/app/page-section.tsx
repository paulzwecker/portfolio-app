import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function PageSection({
  title,
  description,
  actions,
  children,
  id,
  className,
  contentClassName,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  id?: string;
  className?: string;
  contentClassName?: string;
}) {
  const generatedId = useId();
  const headingId = id ?? `section-${generatedId.replaceAll(":", "")}`;

  return (
    <section aria-labelledby={headingId} className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={headingId} className="text-lg font-semibold tracking-tight">
            {title}
          </h2>
          {description && (
            <p className="mt-1 max-w-3xl text-sm leading-5 text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        )}
      </div>
      <div className={cn("min-w-0", contentClassName)}>{children}</div>
    </section>
  );
}
