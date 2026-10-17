import { ArrowUpRight, FileSearch } from "lucide-react";
import { cn } from "@/lib/utils";

export function SourceReference({
  label,
  href,
  reference,
  className,
}: {
  label: string;
  href?: string | null;
  reference?: string | null;
  className?: string;
}) {
  const content = (
    <>
      <FileSearch aria-hidden="true" className="size-3.5 shrink-0" />
      <span className="min-w-0 truncate">{label}</span>
      {reference && (
        <span className="max-w-40 truncate text-muted-foreground">
          {reference}
        </span>
      )}
      {href && <ArrowUpRight aria-hidden="true" className="size-3 shrink-0" />}
    </>
  );

  const classes = cn(
    "inline-flex min-w-0 items-center gap-1.5 text-xs text-primary",
    className,
  );

  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={cn(classes, "underline-offset-4 hover:underline")}
    >
      {content}
    </a>
  ) : (
    <span className={cn(classes, "text-muted-foreground")}>{content}</span>
  );
}
