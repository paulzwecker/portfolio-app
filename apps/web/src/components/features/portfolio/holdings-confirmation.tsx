"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HoldingSnapshot, Overview } from "@/lib/domain-contracts";
import { isSnapshotRead } from "@/lib/domain-contracts";
import { date, quantity } from "@/lib/display";

const decimalInput = /^\d{1,18}(?:\.\d{1,10})?$/;

export function HoldingsConfirmation({
  overview,
  onSaved,
  id,
}: {
  overview: Overview;
  onSaved: (snapshot: HoldingSnapshot) => void;
  id?: string;
}) {
  const snapshot = overview.snapshot;
  const [positionQuantities, setPositionQuantities] = useState<
    Record<string, string>
  >(() =>
    Object.fromEntries(
      (snapshot?.positions ?? []).map((position) => [
        position.listing_id,
        position.quantity ?? "",
      ]),
    ),
  );
  const [cashBalances, setCashBalances] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      (snapshot?.cash_positions ?? []).map((cash) => [
        cash.currency,
        cash.balance ?? "",
      ]),
    ),
  );
  const [reason, setReason] = useState(
    "Investor confirmation of current positions and cash.",
  );
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  if (!snapshot || snapshot.completeness !== "COMPLETE") {
    return (
      <Card className="mb-7 shadow-none">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Holdings confirmation</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            A complete holdings snapshot is required before this workflow can
            reconfirm positions. The current snapshot remains unchanged.
          </p>
        </CardContent>
      </Card>
    );
  }
  const completeSnapshot = snapshot;

  const details = [
    ...overview.companies.flatMap((company) => company.positions),
    ...overview.standalone_positions,
  ];
  const invalidValues =
    completeSnapshot.positions.some(
      (position) =>
        !decimalInput.test(positionQuantities[position.listing_id] ?? ""),
    ) ||
    completeSnapshot.cash_positions.some(
      (cash) => !decimalInput.test(cashBalances[cash.currency] ?? ""),
    );

  function changed() {
    setConfirmed(false);
    setError("");
  }

  async function appendSnapshot() {
    if (!confirmed || invalidValues || !reason.trim()) return;
    setPending(true);
    setError("");
    try {
      const response = await fetch(
        `/api/research/portfolios/${encodeURIComponent(overview.portfolio.id)}/holding-snapshots`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            actor: "LOCAL_USER",
            reason: reason.trim(),
            source: "web-holdings-confirmation",
            effective_at: new Date().toISOString(),
            completeness: "COMPLETE",
            positions: completeSnapshot.positions.map((position) => ({
              listing_id: position.listing_id,
              quantity: positionQuantities[position.listing_id]?.trim(),
            })),
            cash_positions: completeSnapshot.cash_positions.map((cash) => ({
              currency: cash.currency,
              balance: cashBalances[cash.currency]?.trim(),
            })),
          }),
        },
      );
      const result: unknown = await response.json();
      if (!response.ok || !isSnapshotRead(result)) {
        throw new Error(
          "The confirmation was not saved. Check the exact quantities and cash balances, then retry.",
        );
      }
      onSaved(result);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The holdings confirmation could not be saved.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <details id={id} className="rounded-xl border bg-card">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 p-4 [&::-webkit-details-marker]:hidden">
        <span>
          <span className="block text-sm font-semibold">Confirm holdings</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            Latest snapshot {date(snapshot.effective_at)} ·{" "}
            {snapshot.positions.length} listing rows ·{" "}
            {snapshot.cash_positions.length} cash currencies
          </span>
        </span>
        <Badge
          variant={
            overview.holdings_freshness === "FRESH" ? "default" : "secondary"
          }
        >
          {overview.holdings_freshness === "FRESH"
            ? "Current confirmation"
            : "Confirmation needed"}
        </Badge>
      </summary>
      <div className="border-t p-4 sm:p-5">
        <p className="mb-4 max-w-4xl text-xs leading-5 text-muted-foreground">
          Review exact listing quantities and cash in each currency. This action
          appends a new immutable snapshot; it does not change the prior record,
          accepted targets or market prices. Set a fully exited listing to 0.
          The form starts with the listings and cash currencies in the latest
          snapshot.
        </p>
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Security positions
          </h3>
          {snapshot.positions.map((position) => {
            const detail = details.find(
              (item) => item.listing_id === position.listing_id,
            );
            const label = detail
              ? `${detail.security_name} · ${detail.ticker} (${detail.venue}) · ${detail.currency ?? "Currency unknown"}`
              : `Unresolved listing ${position.listing_id}`;
            return (
              <label
                key={position.listing_id}
                className="grid gap-2 rounded-md border p-3 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(150px,220px)] sm:items-center"
              >
                <span className="min-w-0">
                  <span className="block font-medium">{label}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    Exact listing ID {position.listing_id} · recorded{" "}
                    {quantity(position.quantity)} shares
                  </span>
                </span>
                <span>
                  <span className="sr-only">Quantity for {label}</span>
                  <input
                    aria-label={`Quantity for ${detail?.ticker ?? position.listing_id}`}
                    inputMode="decimal"
                    value={positionQuantities[position.listing_id] ?? ""}
                    onChange={(event) => {
                      setPositionQuantities((current) => ({
                        ...current,
                        [position.listing_id]: event.target.value,
                      }));
                      changed();
                    }}
                    className="h-10 w-full rounded-md border bg-background px-3 text-right tabular-nums"
                  />
                </span>
              </label>
            );
          })}
          {snapshot.positions.length === 0 && (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              No security positions were recorded in this complete snapshot.
            </p>
          )}
        </div>

        <div className="mt-5 space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Cash balances
          </h3>
          {snapshot.cash_positions.map((cash) => (
            <label
              key={cash.currency}
              className="grid gap-2 rounded-md border p-3 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(150px,220px)] sm:items-center"
            >
              <span>
                <span className="block font-medium">{cash.currency} cash</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  Recorded {quantity(cash.balance)} {cash.currency}
                </span>
              </span>
              <span>
                <span className="sr-only">Cash balance in {cash.currency}</span>
                <input
                  aria-label={`Cash balance in ${cash.currency}`}
                  inputMode="decimal"
                  value={cashBalances[cash.currency] ?? ""}
                  onChange={(event) => {
                    setCashBalances((current) => ({
                      ...current,
                      [cash.currency]: event.target.value,
                    }));
                    changed();
                  }}
                  className="h-10 w-full rounded-md border bg-background px-3 text-right tabular-nums"
                />
              </span>
            </label>
          ))}
          {snapshot.cash_positions.length === 0 && (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              No cash balances were recorded in this complete snapshot.
            </p>
          )}
        </div>

        <label className="mt-5 block text-xs font-medium">
          Confirmation reason
          <input
            value={reason}
            maxLength={1000}
            onChange={(event) => {
              setReason(event.target.value);
              changed();
            }}
            className="mt-1.5 h-10 w-full rounded-md border bg-background px-3 text-sm"
          />
        </label>
        <label className="mt-4 flex items-start gap-2 text-xs leading-5">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            className="mt-1 size-4 shrink-0 accent-primary"
          />
          <span>
            I have reviewed these share quantities and currency balances and
            confirm they represent the portfolio as of now.
          </span>
        </label>
        {invalidValues && (
          <p className="mt-2 text-xs text-amber-800 dark:text-amber-300">
            Enter non-negative decimal values with at most 10 decimal places;
            use 0 for an exited position or empty cash balance.
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 text-xs text-destructive">
            {error}
          </p>
        )}
        <Button
          type="button"
          className="mt-4 w-full sm:w-auto"
          onClick={appendSnapshot}
          disabled={pending || !confirmed || invalidValues || !reason.trim()}
        >
          {pending ? "Saving confirmation…" : "Append confirmed snapshot"}
        </Button>
      </div>
    </details>
  );
}
