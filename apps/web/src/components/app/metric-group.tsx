import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const columnsClass = {
  1: "sm:grid-cols-1",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-2 xl:grid-cols-3",
  4: "sm:grid-cols-2 xl:grid-cols-4",
} as const;

export function MetricGroup({
  children,
  label,
  columns = 4,
  className,
}: {
  children: ReactNode;
  label: string;
  columns?: keyof typeof columnsClass;
  className?: string;
}) {
  return (
    <div
      aria-label={label}
      className={cn(
        "grid min-w-0 grid-cols-1 gap-3",
        columnsClass[columns],
        className,
      )}
    >
      {children}
    </div>
  );
}
