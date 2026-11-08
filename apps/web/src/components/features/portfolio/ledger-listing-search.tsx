"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  isLedgerListingSearch,
  type LedgerListingSearch,
  type LedgerListingSearchItem,
} from "./ledger-listings";

export function LedgerListingSearch({
  portfolioId,
  disabled,
  onSelect,
}: {
  portfolioId: string;
  disabled: boolean;
  onSelect: (item: LedgerListingSearchItem) => void;
}) {
  const [ticker, setTicker] = useState("");
  const [result, setResult] = useState<LedgerListingSearch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  const search = async () => {
    const requested = ticker.trim();
    if (!requested || requested.length > 40) {
      setError("Enter an exact ticker of at most 40 characters.");
      return;
    }
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setPending(true);
    setResult(null);
    setError(null);
    try {
      const response = await fetch(
        `/api/research/portfolios/${encodeURIComponent(portfolioId)}/ledger/listings?ticker=${encodeURIComponent(requested)}`,
        {
          cache: "no-store",
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(10000),
          ]),
        },
      );
      const data: unknown = await response.json();
      if (
        !response.ok ||
        !isLedgerListingSearch(data) ||
        data.results.some(
          (item) => item.ticker.toUpperCase() !== requested.toUpperCase(),
        )
      )
        throw new Error(
          "Listing search could not be verified. Check the ticker and try again.",
        );
      if (active.current === controller && !controller.signal.aborted)
        setResult(data);
    } catch {
      if (active.current === controller && !controller.signal.aborted)
        setError(
          "Listing search could not be verified. Check the ticker and try again.",
        );
    } finally {
      if (active.current === controller) {
        active.current = null;
        setPending(false);
      }
    }
  };
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <p className="text-sm font-medium">
        Find a listing outside the opening snapshot
      </p>
      <p className="text-xs text-muted-foreground">
        Search an exact ticker, then compare the venue, security, share class
        and currency with your source. A ticker alone does not identify a
        holding. The API verifies the listing identity again during preview;
        names and share class are descriptive context and are not bound to the
        review hash.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-sm">
          Exact listing ticker
          <input
            className="mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm"
            maxLength={40}
            value={ticker}
            disabled={disabled || pending}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void search();
              }
            }}
            onChange={(event) => {
              active.current?.abort();
              active.current = null;
              setPending(false);
              setResult(null);
              setError(null);
              setTicker(event.target.value);
            }}
          />
        </label>
        <Button
          type="button"
          variant="outline"
          disabled={disabled || pending}
          onClick={() => void search()}
        >
          {pending ? "Searching…" : "Search listings"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-warning">
          {error}
        </p>
      )}
      {result && (
        <div aria-live="polite" className="space-y-2">
          {result.truncated && (
            <p className="text-sm text-warning">
              Only the first 50 matching records were checked; eligible matches
              beyond them are not shown.
            </p>
          )}
          {result.unsupported_results && (
            <p className="text-sm text-warning">
              Some matching listings lack a supported currency and are
              unavailable for ledger review.
            </p>
          )}
          {result.results.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No supported listings matched this exact ticker.
            </p>
          )}
          {result.results.map((item) => (
            <div
              className="rounded-md border p-3 text-sm"
              key={item.listing_id}
            >
              <p className="font-medium">
                {item.ticker} · {item.venue} · {item.currency} ·{" "}
                {item.security_type}
                {item.is_demo && " · Demo data"}
              </p>
              <p className="mt-1">
                {item.security_name}
                {item.share_class ? ` · ${item.share_class}` : ""}
                {item.company_name
                  ? ` · ${item.company_name}`
                  : " · No company issuer"}
              </p>
              <p className="mt-1 break-all text-xs text-muted-foreground">
                Listing {item.listing_id} · Security {item.security_id} ·{" "}
                {item.identity_source_ref
                  ? `Identity source ${item.identity_source_ref}`
                  : "Identity source unavailable"}
              </p>
              <Button
                className="mt-2"
                type="button"
                variant="outline"
                disabled={disabled}
                onClick={() => onSelect(item)}
              >
                Use this listing
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
