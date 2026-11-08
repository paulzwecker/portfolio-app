"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { PortfolioLedgerAnchor } from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";
import type { LedgerReviewFile } from "./portfolio-ledger-data";
import { type OpeningAccountDraft } from "./ledger-opening-draft";
import { ledgerAvailableListings, type LedgerListing } from "./ledger-listings";
import {
  buildEndingReview,
  type EndingAccountDraft,
} from "./ledger-ending-draft";

const field =
  "mt-1 block w-full min-w-0 rounded-md border bg-background px-3 py-2 text-sm";

export function LedgerEndingBuilder({
  anchor,
  base,
  opening,
  initialAccounts,
  extraListings = [],
  disabled,
  onChange,
  onReview,
  onClose,
}: {
  anchor: PortfolioLedgerAnchor;
  base: LedgerReviewFile;
  opening: OpeningAccountDraft[];
  initialAccounts?: EndingAccountDraft[];
  extraListings?: readonly LedgerListing[];
  disabled: boolean;
  onChange: () => void;
  onReview: (file: LedgerReviewFile) => Promise<void>;
  onClose: () => void;
}) {
  const [accounts, setAccounts] = useState<EndingAccountDraft[]>(
    () =>
      initialAccounts ??
      opening.map((account) => ({
        accountId: account.id,
        sourceSha256: "",
        sourceRecordId: "",
        positions: [],
        cash: [],
      })),
  );
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const changed = () => {
    onChange();
    setConfirmed(false);
    setError(null);
  };
  const update = (id: string, patch: Partial<EndingAccountDraft>) => {
    changed();
    setAccounts((current) =>
      current.map((account) =>
        account.accountId === id ? { ...account, ...patch } : account,
      ),
    );
  };
  return (
    <div className="space-y-4 rounded-lg border bg-card p-4">
      <p className="text-sm text-muted-foreground">
        Enter observed ending balances for every account at{" "}
        {dateTime(base.asOf)}. Each account requires statement evidence,
        including accounts with no balances.{" "}
        {initialAccounts
          ? "Review the restored amounts against the statements."
          : "Amounts start empty and must come from the statements."}{" "}
        The API compares them with the candidate projection.
      </p>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          try {
            void onReview(
              buildEndingReview(
                anchor,
                base,
                accounts,
                confirmed,
                extraListings,
              ),
            );
          } catch (failure) {
            setError(
              failure instanceof Error
                ? failure.message
                : "Check ending observations.",
            );
          }
        }}
      >
        <fieldset disabled={disabled} className="min-w-0 space-y-4">
          <legend className="sr-only">Ending statement observations</legend>
          {accounts.map((account, index) => (
            <fieldset
              key={account.accountId}
              className="min-w-0 space-y-4 rounded-lg border p-4"
            >
              <legend className="px-1 text-sm font-semibold">
                Ending account {index + 1} ·{" "}
                {opening.find((item) => item.id === account.accountId)?.name ??
                  account.accountId}
              </legend>
              <p className="break-all text-xs text-muted-foreground">
                Account ID {account.accountId}
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-sm">
                  Statement SHA-256
                  <input
                    className={`${field} font-mono text-xs`}
                    maxLength={64}
                    value={account.sourceSha256}
                    onChange={(event) =>
                      update(account.accountId, {
                        sourceSha256: event.target.value,
                      })
                    }
                  />
                </label>
                <label className="text-sm">
                  Statement record reference
                  <input
                    className={field}
                    maxLength={200}
                    value={account.sourceRecordId}
                    onChange={(event) =>
                      update(account.accountId, {
                        sourceRecordId: event.target.value,
                      })
                    }
                  />
                </label>
              </div>
              <div className="space-y-3">
                <p className="text-sm font-medium">Observed positions</p>
                {account.positions.map((row, rowIndex) => (
                  <div
                    key={row.id}
                    className="grid gap-2 rounded-md border p-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto]"
                  >
                    <label className="text-sm">
                      Ending position {rowIndex + 1} listing
                      <select
                        className={field}
                        value={row.listingId}
                        onChange={(event) =>
                          update(account.accountId, {
                            positions: account.positions.map((item) =>
                              item.id === row.id
                                ? { ...item, listingId: event.target.value }
                                : item,
                            ),
                          })
                        }
                      >
                        <option value="">Choose exact listing</option>
                        {ledgerAvailableListings(anchor, extraListings).map(
                          (item) => (
                            <option
                              key={item.listing_id}
                              value={item.listing_id}
                            >
                              {item.venue} · {item.ticker} · {item.currency} ·{" "}
                              {item.security_type}
                            </option>
                          ),
                        )}
                      </select>
                    </label>
                    <label className="text-sm">
                      Ending position {rowIndex + 1} quantity
                      <input
                        className={field}
                        inputMode="decimal"
                        value={row.quantity}
                        onChange={(event) =>
                          update(account.accountId, {
                            positions: account.positions.map((item) =>
                              item.id === row.id
                                ? { ...item, quantity: event.target.value }
                                : item,
                            ),
                          })
                        }
                      />
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      className="self-end"
                      aria-label={`Remove ending position ${rowIndex + 1}`}
                      onClick={() =>
                        update(account.accountId, {
                          positions: account.positions.filter(
                            (item) => item.id !== row.id,
                          ),
                        })
                      }
                    >
                      Remove
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    update(account.accountId, {
                      positions: [
                        ...account.positions,
                        {
                          id: crypto.randomUUID(),
                          listingId: "",
                          quantity: "",
                        },
                      ],
                    })
                  }
                >
                  Add ending position
                </Button>
              </div>
              <div className="space-y-3">
                <p className="text-sm font-medium">Observed cash</p>
                {account.cash.map((row, rowIndex) => (
                  <div
                    key={row.id}
                    className="grid gap-2 rounded-md border p-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]"
                  >
                    <label className="text-sm">
                      Ending cash {rowIndex + 1} currency
                      <input
                        className={field}
                        maxLength={3}
                        value={row.currency}
                        onChange={(event) =>
                          update(account.accountId, {
                            cash: account.cash.map((item) =>
                              item.id === row.id
                                ? { ...item, currency: event.target.value }
                                : item,
                            ),
                          })
                        }
                      />
                    </label>
                    <label className="text-sm">
                      Ending cash {rowIndex + 1} balance
                      <input
                        className={field}
                        inputMode="decimal"
                        value={row.balance}
                        onChange={(event) =>
                          update(account.accountId, {
                            cash: account.cash.map((item) =>
                              item.id === row.id
                                ? { ...item, balance: event.target.value }
                                : item,
                            ),
                          })
                        }
                      />
                    </label>
                    <Button
                      type="button"
                      variant="ghost"
                      className="self-end"
                      aria-label={`Remove ending cash ${rowIndex + 1}`}
                      onClick={() =>
                        update(account.accountId, {
                          cash: account.cash.filter(
                            (item) => item.id !== row.id,
                          ),
                        })
                      }
                    >
                      Remove
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    update(account.accountId, {
                      cash: [
                        ...account.cash,
                        { id: crypto.randomUUID(), currency: "", balance: "" },
                      ],
                    })
                  }
                >
                  Add ending cash
                </Button>
              </div>
            </fieldset>
          ))}
          <p className="text-xs text-muted-foreground">
            Use decimal points and record explicit zero balances where observed.
            Missing and zero rows are evaluated separately.
          </p>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={confirmed}
              onChange={(event) => {
                onChange();
                setConfirmed(event.target.checked);
              }}
            />
            <span>
              I confirm these ending observations are effective at the review
              cutoff.
            </span>
          </label>
          {error && (
            <p role="alert" className="text-sm text-warning">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!confirmed}>
              Reconcile ending statement
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Discard ending statement
            </Button>
          </div>
        </fieldset>
      </form>
    </div>
  );
}
