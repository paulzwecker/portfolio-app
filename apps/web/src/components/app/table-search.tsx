"use client";

import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Presentation-only filtering; callers retain ownership of the underlying rows. */
export function TableSearch({
  label,
  placeholder,
  value,
  onChange,
  resultCount,
  totalCount,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  resultCount: number;
  totalCount: number;
}) {
  return (
    <div className="rounded-lg border bg-muted/60 p-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-0 flex-1 basis-48 text-xs font-medium">
          <span className="mb-1.5 block">{label}</span>
          <span className="relative block">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute top-3 left-3 size-4 text-muted-foreground"
            />
            <input
              type="search"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder={placeholder}
              className="min-h-10 w-full rounded-md border border-input bg-card py-2 pr-3 pl-9 text-sm text-foreground placeholder:text-muted-foreground"
            />
          </span>
        </label>
        <Button
          type="button"
          variant="outline"
          onClick={() => onChange("")}
          disabled={!value}
        >
          Clear search
        </Button>
      </div>
      <p
        role="status"
        aria-live="polite"
        className="mt-2 text-xs text-muted-foreground"
      >
        {resultCount} of {totalCount} rows shown
      </p>
    </div>
  );
}
