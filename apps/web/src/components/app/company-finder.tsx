"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { isUniverseMarketSummary } from "@/lib/domain-contracts";
import { useResearch } from "@/hooks/use-research";
import { saveSelectedCompany } from "@/lib/selected-company";

export function CompanyFinder() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const normalized = query.trim();
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(normalized), 200);
    return () => window.clearTimeout(timer);
  }, [normalized]);
  const encoded = new URLSearchParams({ search: debouncedQuery }).toString();
  const state = useResearch(
    `universe/market-summary?${encoded}`,
    isUniverseMarketSummary,
    0,
    debouncedQuery.length >= 2,
  );
  const results = useMemo(() => (state.data ?? []).slice(0, 8), [state.data]);

  function select(index: number) {
    const row = results[index];
    if (!row) return;
    saveSelectedCompany({
      id: row.company.id,
      name: row.company.name,
      listings: row.market_data.map((market) => ({
        ticker: market.listing.ticker,
        venue: market.listing.venue,
        currency: market.listing.currency ?? null,
      })),
    });
    setOpen(false);
    setQuery("");
    router.push(`/company/${encodeURIComponent(row.company.id)}`);
    inputRef.current?.blur();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" && results.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => (index + 1) % results.length);
    }
    if (event.key === "ArrowUp" && results.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => (index - 1 + results.length) % results.length);
    }
    if (event.key === "Enter" && open && results.length > 0) {
      event.preventDefault();
      select(activeIndex);
    }
  }

  return (
    <div className="relative min-w-0">
      <label htmlFor="company-finder" className="sr-only">
        Search companies and listings
      </label>
      <div className="flex h-10 items-center gap-2 rounded-md border bg-background px-3 focus-within:ring-2 focus-within:ring-ring">
        <Search
          aria-hidden="true"
          className="size-4 shrink-0 text-muted-foreground"
        />
        <input
          ref={inputRef}
          id="company-finder"
          type="search"
          autoComplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open && normalized.length >= 2}
          aria-controls="company-finder-results"
          aria-activedescendant={
            open && results[activeIndex]
              ? `company-result-${results[activeIndex]!.company.id}`
              : undefined
          }
          placeholder="Company or ticker"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setActiveIndex(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={handleKeyDown}
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      {open && normalized.length >= 2 && (
        <div
          id="company-finder-results"
          role="listbox"
          aria-label="Matching companies and listings"
          className="absolute left-0 top-[calc(100%+0.35rem)] z-50 max-h-80 w-[min(22rem,calc(100vw-2rem))] overflow-y-auto rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg md:w-[min(22rem,calc(100vw-3rem))]"
        >
          {state.error ? (
            <p
              role="status"
              className="px-3 py-3 text-sm text-muted-foreground"
            >
              Search is unavailable. Check the API connection and retry.
            </p>
          ) : normalized !== debouncedQuery || !state.data ? (
            <p
              role="status"
              className="px-3 py-3 text-sm text-muted-foreground"
            >
              Searching canonical companies and listings…
            </p>
          ) : results.length === 0 ? (
            <p
              role="status"
              className="px-3 py-3 text-sm text-muted-foreground"
            >
              No matching companies or listings.
            </p>
          ) : (
            results.map((row, index) => {
              const listingSummary = row.market_data
                .slice(0, 3)
                .map(
                  ({ listing }) =>
                    `${listing.ticker} · ${listing.venue} · ${listing.currency ?? "currency unknown"}`,
                )
                .join("  /  ");
              return (
                <button
                  key={row.company.id}
                  id={`company-result-${row.company.id}`}
                  type="button"
                  role="option"
                  aria-selected={activeIndex === index}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => select(index)}
                  className={`flex w-full flex-col rounded-md px-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-ring ${activeIndex === index ? "bg-accent" : "hover:bg-accent/70"}`}
                >
                  <span className="text-sm font-medium">
                    {row.company.name}
                  </span>
                  <span className="mt-0.5 truncate text-xs text-muted-foreground">
                    {listingSummary || "No listing recorded"}
                  </span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
