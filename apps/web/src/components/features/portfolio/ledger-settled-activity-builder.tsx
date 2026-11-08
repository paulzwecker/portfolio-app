"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { PortfolioLedgerAnchor } from "@/lib/domain-contracts";
import type { LedgerReviewFile } from "./portfolio-ledger-data";
import { restoreOpeningReview } from "./ledger-opening-draft";
import {
  buildSettledActivityReview,
  type SettledActivityDraft,
} from "./ledger-settled-activity";

const field =
  "mt-1 block w-full min-w-0 rounded-md border bg-background px-3 py-2 text-sm";

export function LedgerSettledActivityBuilder({
  anchor,
  base,
  disabled,
  initialCutoff = "",
  initialEntries = [],
  onChange,
  onReview,
  onClose,
}: {
  anchor: PortfolioLedgerAnchor;
  base: LedgerReviewFile;
  disabled: boolean;
  initialCutoff?: string;
  initialEntries?: SettledActivityDraft[];
  onChange: () => void;
  onReview: (file: LedgerReviewFile) => Promise<void>;
  onClose: () => void;
}) {
  const [accounts] = useState(() =>
    restoreOpeningReview(anchor, base.text).filter(
      (account) => account.kind === "BROKERAGE",
    ),
  );
  const [cutoff, setCutoff] = useState(initialCutoff);
  const [entries, setEntries] =
    useState<SettledActivityDraft[]>(initialEntries);
  const [error, setError] = useState<string | null>(null);
  const changed = () => {
    onChange();
    setError(null);
  };
  const update = (id: string, patch: Partial<SettledActivityDraft>) => {
    changed();
    setEntries((current) =>
      current.map((entry) =>
        entry.id === id ? { ...entry, ...patch } : entry,
      ),
    );
  };

  return (
    <div className="space-y-4 rounded-lg border bg-card p-4">
      <p className="text-sm text-muted-foreground">
        Enter settled purchases, sales, dividends, deposits, withdrawals, fees,
        taxes or internal cash transfers from your records. Trades and dividends
        require a listing in the verified anchor. Dividend currency is the
        received cash currency and can differ from the listing currency; no
        conversion is inferred. Enter timestamps with seconds and a UTC offset,
        for example 2026-01-15T10:30:00+01:00. The sequence determines ordering
        when booking times match. The API checks the complete reconstruction.
      </p>
      <p className="text-xs text-muted-foreground">
        Discard this activity draft before changing the opening or loading
        another file.
      </p>
      {accounts.length === 0 && (
        <p className="text-sm text-warning">
          Activity requires an evidenced brokerage account in the opening
          review.
        </p>
      )}
      {accounts.length === 1 && (
        <p className="text-sm text-muted-foreground">
          Internal cash transfers require two evidenced brokerage accounts in
          the opening review.
        </p>
      )}
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          try {
            void onReview(
              buildSettledActivityReview(anchor, base, cutoff, entries),
            );
          } catch (failure) {
            setError(
              failure instanceof Error
                ? failure.message
                : "Check the activity records.",
            );
          }
        }}
      >
        <fieldset disabled={disabled} className="min-w-0 space-y-4">
          <legend className="sr-only">Settled activity</legend>
          <label className="block text-sm">
            Review cutoff timestamp
            <input
              className={field}
              value={cutoff}
              placeholder="2026-01-31T23:59:59+01:00"
              onChange={(event) => {
                changed();
                setCutoff(event.target.value);
              }}
            />
          </label>
          {entries.map((entry, index) => (
            <fieldset
              key={entry.id}
              className="min-w-0 space-y-4 rounded-lg border p-4"
            >
              <legend className="px-1 text-sm font-semibold">
                Activity record {index + 1}
              </legend>
              {entry.kind === "DIVIDEND" && (
                <p className="text-xs text-muted-foreground">
                  Enter the evidenced gross receipt, fees and withholding in the
                  received cash currency. Fees plus withholding cannot exceed
                  gross cash. Do not enter the same withholding again as a
                  separate tax.
                </p>
              )}
              {entry.kind === "CASH_TRANSFER" && (
                <p className="text-xs text-muted-foreground">
                  Enter both independently evidenced legs. Accounts must differ;
                  currency, amount and booking instant must match. Transfers are
                  not deposits or withdrawals. FX and unmatched legs require a
                  different review.
                </p>
              )}
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-sm">
                  Account
                  <select
                    className={field}
                    value={entry.accountId}
                    onChange={(event) =>
                      update(entry.id, { accountId: event.target.value })
                    }
                  >
                    <option value="">Choose account</option>
                    {accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.name} · {account.brokerName} · {account.id}
                      </option>
                    ))}
                  </select>
                  {entry.accountId && (
                    <span className="mt-1 block break-all text-xs text-muted-foreground">
                      Account ID {entry.accountId}
                    </span>
                  )}
                </label>
                <label className="text-sm">
                  Type
                  <select
                    className={field}
                    disabled={entry.kind !== ""}
                    value={entry.kind}
                    onChange={(event) =>
                      update(entry.id, {
                        kind: event.target
                          .value as SettledActivityDraft["kind"],
                      })
                    }
                  >
                    <option value="">Choose type</option>
                    <option value="BUY">Purchase</option>
                    <option value="SELL">Sale</option>
                    <option value="DIVIDEND">Dividend</option>
                    <option
                      value="CASH_TRANSFER"
                      disabled={accounts.length < 2}
                    >
                      Internal cash transfer
                    </option>
                    <option value="DEPOSIT">Deposit</option>
                    <option value="WITHDRAWAL">Withdrawal</option>
                    <option value="FEE">Fee</option>
                    <option value="TAX">Tax</option>
                  </select>
                </label>
                <label className="text-sm">
                  Booking timestamp
                  <input
                    className={field}
                    value={entry.effectiveAt}
                    placeholder="2026-01-15T10:30:00+01:00"
                    onChange={(event) =>
                      update(entry.id, { effectiveAt: event.target.value })
                    }
                  />
                </label>
                <label className="text-sm">
                  Sequence
                  <input
                    className={field}
                    inputMode="numeric"
                    value={entry.sequence}
                    onChange={(event) =>
                      update(entry.id, { sequence: event.target.value })
                    }
                  />
                </label>
                <label className="text-sm">
                  {entry.kind === "DIVIDEND"
                    ? "Received cash currency"
                    : "Currency"}
                  <input
                    className={field}
                    maxLength={3}
                    value={entry.currency}
                    onChange={(event) =>
                      update(entry.id, { currency: event.target.value })
                    }
                  />
                </label>
                {entry.kind === "BUY" ||
                entry.kind === "SELL" ||
                entry.kind === "DIVIDEND" ? (
                  <>
                    <label className="text-sm">
                      Listing
                      <select
                        className={field}
                        value={entry.listingId ?? ""}
                        onChange={(event) =>
                          update(entry.id, { listingId: event.target.value })
                        }
                      >
                        <option value="">Choose verified listing</option>
                        {anchor.listings.map((listing) => (
                          <option
                            key={listing.listing_id}
                            value={listing.listing_id}
                          >
                            {listing.ticker} · {listing.venue} ·{" "}
                            {listing.currency} · {listing.listing_id}
                          </option>
                        ))}
                      </select>
                    </label>
                    {(
                      (entry.kind === "DIVIDEND"
                        ? [
                            ["Gross dividend cash", "grossCash"],
                            ["Fees", "fees"],
                            ["Taxes withheld", "taxes"],
                          ]
                        : [
                            ["Quantity", "quantity"],
                            ["Gross settlement cash", "grossCash"],
                            ["Fees", "fees"],
                            ["Taxes", "taxes"],
                            ["Trade date", "tradeDate"],
                            ["Settlement date", "settlementDate"],
                          ]) as ReadonlyArray<
                        readonly [
                          string,
                          (
                            | "quantity"
                            | "grossCash"
                            | "fees"
                            | "taxes"
                            | "tradeDate"
                            | "settlementDate"
                          ),
                        ]
                      >
                    ).map(([label, key]) => (
                      <label className="text-sm" key={key}>
                        {label}
                        <input
                          className={field}
                          inputMode={
                            key.endsWith("Date") ? undefined : "decimal"
                          }
                          placeholder={
                            key.endsWith("Date") ? "YYYY-MM-DD" : undefined
                          }
                          value={entry[key] ?? ""}
                          onChange={(event) =>
                            update(entry.id, { [key]: event.target.value })
                          }
                        />
                      </label>
                    ))}
                  </>
                ) : entry.kind ? (
                  <label className="text-sm">
                    Amount
                    <input
                      className={field}
                      inputMode="decimal"
                      value={entry.amount}
                      onChange={(event) =>
                        update(entry.id, { amount: event.target.value })
                      }
                    />
                  </label>
                ) : null}
                <label className="text-sm">
                  Source document SHA-256
                  <input
                    className={`${field} font-mono text-xs`}
                    maxLength={64}
                    value={entry.sourceSha256}
                    onChange={(event) =>
                      update(entry.id, { sourceSha256: event.target.value })
                    }
                  />
                </label>
                <label className="text-sm">
                  Source record reference
                  <input
                    className={field}
                    maxLength={200}
                    value={entry.sourceRecordId}
                    onChange={(event) =>
                      update(entry.id, { sourceRecordId: event.target.value })
                    }
                  />
                </label>
                {entry.kind === "CASH_TRANSFER" && (
                  <>
                    <label className="text-sm">
                      Destination account
                      <select
                        className={field}
                        value={entry.destinationAccountId ?? ""}
                        onChange={(event) =>
                          update(entry.id, {
                            destinationAccountId: event.target.value,
                          })
                        }
                      >
                        <option value="">Choose destination account</option>
                        {accounts.map((account) => (
                          <option key={account.id} value={account.id}>
                            {account.name} · {account.brokerName} · {account.id}
                          </option>
                        ))}
                      </select>
                      {entry.destinationAccountId && (
                        <span className="mt-1 block break-all text-xs text-muted-foreground">
                          Destination account ID {entry.destinationAccountId}
                        </span>
                      )}
                    </label>
                    {(
                      [
                        ["Destination currency", "destinationCurrency"],
                        ["Destination amount", "destinationAmount"],
                        [
                          "Destination booking timestamp",
                          "destinationEffectiveAt",
                        ],
                        [
                          "Destination source document SHA-256",
                          "destinationSourceSha256",
                        ],
                        [
                          "Destination source record reference",
                          "destinationSourceRecordId",
                        ],
                      ] as const
                    ).map(([label, key]) => (
                      <label className="text-sm" key={key}>
                        {label}
                        <input
                          className={field}
                          inputMode={
                            key === "destinationAmount" ? "decimal" : undefined
                          }
                          value={entry[key] ?? ""}
                          onChange={(event) =>
                            update(entry.id, { [key]: event.target.value })
                          }
                        />
                      </label>
                    ))}
                  </>
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  changed();
                  setEntries((current) =>
                    current.filter((item) => item.id !== entry.id),
                  );
                }}
              >
                Remove activity record {index + 1}
              </Button>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            disabled={accounts.length === 0 || entries.length >= 1000}
            onClick={() => {
              changed();
              setEntries((current) => [
                ...current,
                {
                  id: crypto.randomUUID(),
                  accountId: "",
                  kind: "",
                  sequence: "",
                  effectiveAt: "",
                  currency: "",
                  amount: "",
                  sourceSha256: "",
                  sourceRecordId: "",
                },
              ]);
            }}
          >
            Add activity record
          </Button>
          <p className="text-xs text-muted-foreground">
            Use exact decimals in the recorded currency. Enter zero explicitly
            for no fees or taxes. Keep each source record distinct. To change a
            selected type, remove the record and add it again.
          </p>
          {error && (
            <p role="alert" className="text-sm text-warning">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={entries.length === 0}>
              Review activity
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>
              Discard activity
            </Button>
          </div>
        </fieldset>
      </form>
    </div>
  );
}
