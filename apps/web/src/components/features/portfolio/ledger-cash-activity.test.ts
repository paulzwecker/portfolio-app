import { expect, it } from "vitest";
import { ledgerAnchor, ledgerAccountId } from "../../../../e2e/fixtures/ledger";
import {
  buildOpeningReview,
  type OpeningAccountDraft,
} from "./ledger-opening-draft";
import {
  buildCashActivityReview,
  type CashActivityDraft,
} from "./ledger-cash-activity";

const opening: OpeningAccountDraft = {
  id: ledgerAccountId,
  name: "Synthetic account",
  kind: "BROKERAGE",
  brokerName: "Synthetic broker",
  sourceSha256: "b".repeat(64),
  sourceRecordId: "opening",
  hashing: false,
  positions: [
    {
      id: "position",
      listingId: ledgerAnchor.listings[0].listing_id,
      quantity: "2.5000000000",
    },
  ],
  cash: [
    { id: "cash", currency: "USD", balance: "100.0000000000" },
    { id: "zero", currency: "EUR", balance: "0" },
  ],
};
const base = buildOpeningReview(ledgerAnchor, [opening], true);
const cutoff = "2026-01-31T23:59:59+01:00";
function record(): CashActivityDraft {
  return {
    id: "66666666-6666-4666-8666-666666666666",
    accountId: ledgerAccountId,
    kind: "DEPOSIT",
    sequence: "1",
    effectiveAt: "2026-01-15T10:30:00+01:00",
    currency: "USD",
    amount: "9007199254740993.1234567890",
    sourceSha256: "c".repeat(64),
    sourceRecordId: "deposit-1",
  };
}

it("builds deterministic cash records preserving the exact opening and decimal text", () => {
  const first = record();
  const second = {
    ...record(),
    id: "77777777-7777-4777-8777-777777777777",
    kind: "TAX" as const,
    sequence: "2",
    amount: "0.0000000001",
    sourceRecordId: "tax-1",
  };
  const result = buildCashActivityReview(ledgerAnchor, base, cutoff, [
    first,
    second,
  ]);
  const packet = JSON.parse(result.text);
  expect(packet.accounts).toEqual(JSON.parse(base.text).accounts);
  expect(packet.as_of).toBe(cutoff);
  expect(packet.ending_statement).toBeNull();
  expect(packet.activity[0]).toEqual({
    id: first.id,
    account_id: first.accountId,
    kind: "DEPOSIT",
    sequence: 1,
    effective_at: first.effectiveAt,
    currency: "USD",
    amount: first.amount,
    evidence: {
      source_sha256: first.sourceSha256,
      source_record_id: first.sourceRecordId,
    },
  });
  expect(packet.activity[1].amount).toBe("0.0000000001");
  expect(result.evidence).toHaveLength(3);
  expect(
    buildCashActivityReview(ledgerAnchor, base, cutoff, [first, second]).text,
  ).toBe(result.text);
});

it.each([
  { accountId: "unrelated" },
  { kind: "" as const },
  { sequence: "0" },
  { sequence: "1.0" },
  { effectiveAt: "2026-01-15T10:30:00" },
  { currency: "usd" },
  { amount: "0" },
  { amount: "1e3" },
  { amount: "" },
  { sourceSha256: "" },
  { sourceRecordId: " " },
])("rejects incomplete or ambiguous cash evidence %j", (change) => {
  expect(() =>
    buildCashActivityReview(ledgerAnchor, base, cutoff, [
      { ...record(), ...change },
    ]),
  ).toThrow();
});

it("rejects reused source keys and sequences, stale anchors and unallocated accounts", () => {
  expect(() =>
    buildCashActivityReview(ledgerAnchor, base, "2026-01-31", [record()]),
  ).toThrow(/offset/);
  expect(() => buildCashActivityReview(ledgerAnchor, base, cutoff, [])).toThrow(
    /one and/,
  );
  expect(() =>
    buildCashActivityReview(ledgerAnchor, base, cutoff, [
      {
        ...record(),
        sourceSha256: opening.sourceSha256,
        sourceRecordId: " opening ",
      },
    ]),
  ).toThrow(/duplicates/);
  const other = {
    ...record(),
    id: "77777777-7777-4777-8777-777777777777",
    sourceRecordId: "other",
  };
  expect(() =>
    buildCashActivityReview(ledgerAnchor, base, cutoff, [record(), other]),
  ).toThrow(/sequence/);
  expect(() =>
    buildCashActivityReview(
      { ...ledgerAnchor, anchor_sha256: "f".repeat(64) },
      base,
      cutoff,
      [record()],
    ),
  ).toThrow(/current anchor/);
  const unallocated = buildOpeningReview(
    ledgerAnchor,
    [{ ...opening, kind: "UNALLOCATED_OPENING", brokerName: "" }],
    true,
  );
  expect(() =>
    buildCashActivityReview(ledgerAnchor, unallocated, cutoff, [record()]),
  ).toThrow(/brokerage/);
});
