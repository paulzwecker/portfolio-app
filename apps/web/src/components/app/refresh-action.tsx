"use client";

import { RefreshCw } from "lucide-react";
import { useId } from "react";
import { Button } from "@/components/ui/button";

export function RefreshAction({
  children,
  disabled,
  pending = false,
  variant = "outline",
  disabledReason,
  onClick,
}: {
  children: string;
  disabled?: boolean;
  pending?: boolean;
  variant?: "default" | "outline" | "secondary" | "ghost";
  disabledReason?: string;
  onClick: () => void;
}) {
  const descriptionId = useId();
  return (
    <span className="inline-flex min-w-0 flex-col items-start gap-1">
      <Button
        type="button"
        variant={variant}
        disabled={disabled || pending}
        aria-describedby={disabledReason ? descriptionId : undefined}
        title={disabledReason}
        onClick={onClick}
      >
        <RefreshCw
          aria-hidden="true"
          className={pending ? "animate-spin" : undefined}
        />
        {pending ? "Queuing refresh…" : children}
      </Button>
      {disabledReason && (
        <span
          id={descriptionId}
          className="max-w-full text-xs text-muted-foreground"
        >
          {disabledReason}
        </span>
      )}
    </span>
  );
}
