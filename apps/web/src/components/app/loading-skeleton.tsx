import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

export function LoadingSkeleton({
  lines = 3,
  label = "Loading content",
  className,
}: {
  lines?: number;
  label?: string;
  className?: string;
}) {
  return (
    <div className={cn("w-full space-y-3", className)} aria-label={label}>
      {Array.from({ length: Math.max(1, lines) }, (_, index) => (
        <Skeleton
          key={index}
          aria-hidden="true"
          className={cn(
            "h-4",
            index === 0 ? "w-2/5" : index === lines - 1 ? "w-3/5" : "w-full",
          )}
        />
      ))}
    </div>
  );
}
