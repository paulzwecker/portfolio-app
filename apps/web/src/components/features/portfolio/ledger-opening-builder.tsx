"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { PortfolioLedgerAnchor } from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";
import {
  ledgerFileLimit,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";
import {
  buildOpeningReview,
  hashOpeningStatement,
  restoreOpeningReview,
  type OpeningAccountDraft,
} from "./ledger-opening-draft";

const fieldClass =
  "mt-1 block w-full min-w-0 rounded-md border bg-background px-3 py-2 text-sm";

export function LedgerOpeningBuilder({
  anchor,
  disabled,
  onChange,
  onReview,
  collapsed = false,
}: {
  anchor: PortfolioLedgerAnchor;
  disabled: boolean;
  onChange: () => void;
  onReview: (file: LedgerReviewFile) => Promise<void>;
  collapsed?: boolean;
}) {
  const [accounts, setAccounts] = useState<OpeningAccountDraft[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hashes = useRef(new Map<string, number>());
  const hashVersion = useRef(0);
  const restoreVersion = useRef(0);
  useEffect(
    () => () => {
      hashes.current.clear();
      restoreVersion.current += 1;
    },
    [],
  );

  const changed = () => {
    restoreVersion.current += 1;
    onChange();
    setConfirmed(false);
    setError(null);
  };
  const restore = async (file: File | undefined) => {
    const version = ++restoreVersion.current;
    if (!file) return;
    onChange();
    setError(null);
    try {
      if (file.size > ledgerFileLimit)
        throw new Error("Choose an opening review JSON smaller than 1 MB.");
      const text = new TextDecoder("utf-8", { fatal: true }).decode(
        await file.arrayBuffer(),
      );
      const restored = restoreOpeningReview(anchor, text);
      if (version !== restoreVersion.current) return;
      hashes.current.clear();
      changed();
      setAccounts(restored);
    } catch (failure) {
      if (version === restoreVersion.current)
        setError(
          failure instanceof Error && failure.name !== "TypeError"
            ? failure.message
            : "Choose a valid UTF-8 opening review JSON.",
        );
    }
  };
  const update = (id: string, patch: Partial<OpeningAccountDraft>) => {
    changed();
    setAccounts((current) =>
      current.map((account) =>
        account.id === id ? { ...account, ...patch } : account,
      ),
    );
  };
  const hashStatement = async (id: string, file: File | undefined) => {
    const version = ++hashVersion.current;
    hashes.current.set(id, version);
    update(id, { sourceSha256: "", hashing: Boolean(file) });
    if (!file) return;
    try {
      const digest = await hashOpeningStatement(file);
      if (hashes.current.get(id) === version)
        update(id, { sourceSha256: digest, hashing: false });
    } catch (failure) {
      if (hashes.current.get(id) === version) {
        update(id, { hashing: false });
        setError(
          failure instanceof Error
            ? failure.message
            : "Statement hashing is unavailable.",
        );
      }
    }
  };
  const busy = accounts.some((account) => account.hashing);
  return (
    <details className="rounded-lg border bg-card p-4" open={!collapsed}>
      <summary className="cursor-pointer font-medium">
        Build an opening review
      </summary>
      <p className="mt-3 text-sm text-muted-foreground">
        Declare each account and its statement balances as of{" "}
        {dateTime(anchor.snapshot.effective_at)}. Quantities and cash are
        reconciled by the application API. Acquisition basis remains unavailable
        in this opening contract.
      </p>
      <label className="mt-3 block text-sm">
        Replace draft from downloaded opening review JSON
        <input
          type="file"
          accept=".json,application/json"
          className={fieldClass}
          disabled={disabled}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            void restore(file);
          }}
        />
      </label>
      <p className="mt-1 text-xs text-muted-foreground">
        The downloaded opening packet restores accounts and balances in this
        page. Confirm its source date again before review.
      </p>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer">
          View observed balance reference
        </summary>
        <ul className="mt-2 space-y-1">
          {anchor.snapshot.positions.map((position) => {
            const listing = anchor.listings.find(
              (item) => item.listing_id === position.listing_id,
            );
            return (
              <li key={position.listing_id} className="break-words">
                {listing
                  ? `${listing.venue} · ${listing.ticker} · ${listing.currency}`
                  : position.listing_id}{" "}
                · {position.quantity ?? "Unavailable"}
              </li>
            );
          })}
          {anchor.snapshot.cash_positions.map((cash) => (
            <li key={cash.currency}>
              {cash.currency} cash · {cash.balance ?? "Unavailable"}
            </li>
          ))}
        </ul>
      </details>
      <form
        className="mt-4 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          try {
            void onReview(buildOpeningReview(anchor, accounts, confirmed));
          } catch (failure) {
            setError(
              failure instanceof Error
                ? failure.message
                : "Check the opening fields.",
            );
          }
        }}
      >
        <fieldset disabled={disabled} className="min-w-0 space-y-4">
          <legend className="sr-only">Opening balance source entry</legend>
          {accounts.map((account, index) => (
            <fieldset
              key={account.id}
              className="min-w-0 space-y-4 rounded-lg border p-4"
            >
              <legend className="px-1 text-sm font-semibold">
                Opening account {index + 1}
              </legend>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-sm">
                  Account name
                  <input
                    className={fieldClass}
                    value={account.name}
                    maxLength={200}
                    onChange={(event) =>
                      update(account.id, { name: event.target.value })
                    }
                  />
                </label>
                <label className="text-sm">
                  Account classification
                  <select
                    className={fieldClass}
                    value={account.kind}
                    onChange={(event) =>
                      update(account.id, {
                        kind: event.target.value as OpeningAccountDraft["kind"],
                        brokerName: "",
                      })
                    }
                  >
                    <option value="BROKERAGE">
                      Evidenced brokerage account
                    </option>
                    <option value="UNALLOCATED_OPENING">
                      Explicit unallocated opening
                    </option>
                  </select>
                </label>
                {account.kind === "BROKERAGE" && (
                  <label className="text-sm">
                    Broker name
                    <input
                      className={fieldClass}
                      value={account.brokerName}
                      maxLength={200}
                      onChange={(event) =>
                        update(account.id, { brokerName: event.target.value })
                      }
                    />
                  </label>
                )}
                <label className="text-sm">
                  Statement reference
                  <input
                    className={fieldClass}
                    value={account.sourceRecordId}
                    maxLength={200}
                    onChange={(event) =>
                      update(account.id, { sourceRecordId: event.target.value })
                    }
                  />
                </label>
              </div>
              <label className="block text-sm">
                Hash a private statement file
                <input
                  type="file"
                  className={fieldClass}
                  onChange={(event) =>
                    void hashStatement(account.id, event.target.files?.[0])
                  }
                />
              </label>
              <p className="text-xs text-muted-foreground">
                Files are hashed locally, up to 10 MiB. Review sends the
                document hash and entered balances to the authenticated API.
              </p>
              <label className="block text-sm">
                Source document SHA-256
                <input
                  className={`${fieldClass} font-mono text-xs`}
                  value={account.sourceSha256}
                  maxLength={64}
                  onChange={(event) => {
                    hashes.current.set(account.id, ++hashVersion.current);
                    update(account.id, {
                      sourceSha256: event.target.value,
                      hashing: false,
                    });
                  }}
                />
              </label>
              {account.hashing && (
                <p role="status" className="text-sm">
                  Hashing private statement…
                </p>
              )}
              <div className="space-y-3">
                <p className="text-sm font-medium">Opening positions</p>
                {account.positions.map((row, rowIndex) => (
                  <div
                    key={row.id}
                    className="grid gap-2 rounded-md border p-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto]"
                  >
                    <label className="text-sm">
                      Position {rowIndex + 1} listing
                      <select
                        className={fieldClass}
                        value={row.listingId}
                        onChange={(event) =>
                          update(account.id, {
                            positions: account.positions.map((item) =>
                              item.id === row.id
                                ? { ...item, listingId: event.target.value }
                                : item,
                            ),
                          })
                        }
                      >
                        <option value="">Choose an exact listing</option>
                        {anchor.listings.map((listing) => (
                          <option
                            key={listing.listing_id}
                            value={listing.listing_id}
                          >
                            {listing.venue} · {listing.ticker} ·{" "}
                            {listing.currency} · {listing.security_type}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-sm">
                      Position {rowIndex + 1} quantity
                      <input
                        className={fieldClass}
                        inputMode="decimal"
                        value={row.quantity}
                        onChange={(event) =>
                          update(account.id, {
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
                      aria-label={`Remove position ${rowIndex + 1}`}
                      onClick={() =>
                        update(account.id, {
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
                    update(account.id, {
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
                  Add position
                </Button>
              </div>
              <div className="space-y-3">
                <p className="text-sm font-medium">Opening cash</p>
                {account.cash.map((row, rowIndex) => (
                  <div
                    key={row.id}
                    className="grid gap-2 rounded-md border p-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]"
                  >
                    <label className="text-sm">
                      Cash {rowIndex + 1} currency
                      <input
                        className={fieldClass}
                        value={row.currency}
                        maxLength={3}
                        placeholder="EUR"
                        onChange={(event) =>
                          update(account.id, {
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
                      Cash {rowIndex + 1} balance
                      <input
                        className={fieldClass}
                        inputMode="decimal"
                        value={row.balance}
                        onChange={(event) =>
                          update(account.id, {
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
                      aria-label={`Remove cash ${rowIndex + 1}`}
                      onClick={() =>
                        update(account.id, {
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
                    update(account.id, {
                      cash: [
                        ...account.cash,
                        { id: crypto.randomUUID(), currency: "", balance: "" },
                      ],
                    })
                  }
                >
                  Add cash balance
                </Button>
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  changed();
                  hashes.current.delete(account.id);
                  setAccounts((current) =>
                    current.filter((item) => item.id !== account.id),
                  );
                }}
              >
                Remove account
              </Button>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            disabled={accounts.length >= 20}
            onClick={() => {
              changed();
              setAccounts((current) => [
                ...current,
                {
                  id: crypto.randomUUID(),
                  name: "",
                  kind: "BROKERAGE",
                  brokerName: "",
                  sourceSha256: "",
                  sourceRecordId: "",
                  hashing: false,
                  positions: [],
                  cash: [],
                },
              ]);
            }}
          >
            Add opening account
          </Button>
          <p className="text-xs text-muted-foreground">
            Enter decimal values with a dot. Enter explicit zeros where the
            source records them. Each cash currency and exact listing can appear
            once per account.
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
              I confirm the entered source balances are as of the observed
              anchor date.
            </span>
          </label>
          {error && (
            <p role="alert" className="text-sm text-warning">
              {error}
            </p>
          )}
          <Button
            type="submit"
            disabled={accounts.length === 0 || !confirmed || busy}
          >
            {disabled
              ? "Reviewing opening balances…"
              : "Reconcile opening balances"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="ml-2"
            disabled={accounts.length === 0}
            onClick={() => {
              changed();
              hashes.current.clear();
              setAccounts([]);
            }}
          >
            Clear opening draft
          </Button>
        </fieldset>
      </form>
    </details>
  );
}
