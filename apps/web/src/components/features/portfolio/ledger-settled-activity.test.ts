import { expect, it } from "vitest";
import { ledgerAnchor, ledgerAccountId } from "../../../../e2e/fixtures/ledger";
import {
  buildOpeningReview,
  type OpeningAccountDraft,
} from "./ledger-opening-draft";
import {
  buildSettledActivityReview,
  restoreSettledActivityReview,
  type SettledActivityDraft,
} from "./ledger-settled-activity";

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
function record(): SettledActivityDraft {
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

it("restores exact cash packets with their original identities, evidence and precision", () => {
  const first = record();
  const second = {
    ...record(),
    id: "77777777-7777-4777-8777-777777777777",
    kind: "FEE" as const,
    sequence: "2",
    amount: "0.0000000001",
    sourceRecordId: "fee-1",
  };
  const original = buildSettledActivityReview(ledgerAnchor, base, cutoff, [
    first,
    second,
  ]);
  const restored = restoreSettledActivityReview(ledgerAnchor, original.text);
  expect(restored.entries).toEqual([first, second]);
  expect(restored.cutoff).toBe(cutoff);
  expect(restored.base.text).toBe(base.text);
  expect(
    buildSettledActivityReview(
      ledgerAnchor,
      restored.base,
      restored.cutoff,
      restored.entries,
    ).text,
  ).toBe(original.text);
});

it("rejects stale, lossy, unsupported or extended packets without discarding data", () => {
  const text = buildSettledActivityReview(ledgerAnchor, base, cutoff, [
    record(),
  ]).text;
  type FixturePacket = {
    activity: { kind: string; amount: string | number; unknown?: string }[];
    ending_statement: unknown;
    accounts: { cash: { balance: string | number }[] }[];
  };
  const altered = (change: (packet: FixturePacket) => void) => {
    const packet = JSON.parse(text) as FixturePacket;
    change(packet);
    return JSON.stringify(packet);
  };
  for (const candidate of [
    "{bad",
    text + " ",
    altered((packet) => {
      packet.activity[0].kind = "DIVIDEND";
    }),
    altered((packet) => {
      packet.activity[0].amount = 9007199254740992;
    }),
    altered((packet) => {
      packet.activity[0].unknown = "evidence";
    }),
    altered((packet) => {
      packet.ending_statement = { accounts: [] };
    }),
    altered((packet) => {
      packet.activity = [];
    }),
    altered((packet) => {
      packet.accounts[0].cash[0].balance = 0;
    }),
  ])
    expect(() => restoreSettledActivityReview(ledgerAnchor, candidate)).toThrow(
      /cannot be edited/,
    );
  expect(() =>
    restoreSettledActivityReview(
      { ...ledgerAnchor, anchor_sha256: "f".repeat(64) },
      text,
    ),
  ).toThrow(/cannot be edited/);
});

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
  const result = buildSettledActivityReview(ledgerAnchor, base, cutoff, [
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
    buildSettledActivityReview(ledgerAnchor, base, cutoff, [first, second])
      .text,
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
    buildSettledActivityReview(ledgerAnchor, base, cutoff, [
      { ...record(), ...change },
    ]),
  ).toThrow();
});

it("rejects reused source keys and sequences, stale anchors and unallocated accounts", () => {
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, base, "2026-01-31", [record()]),
  ).toThrow(/offset/);
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, base, cutoff, []),
  ).toThrow(/one and/);
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, base, cutoff, [
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
    buildSettledActivityReview(ledgerAnchor, base, cutoff, [record(), other]),
  ).toThrow(/sequence/);
  expect(() =>
    buildSettledActivityReview(
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
    buildSettledActivityReview(ledgerAnchor, unallocated, cutoff, [record()]),
  ).toThrow(/brokerage/);
});

function trade(kind: "BUY" | "SELL" = "BUY"): SettledActivityDraft {
  return {
    ...record(),
    id: "77777777-7777-4777-8777-777777777777",
    kind,
    sequence: "2",
    amount: "",
    listingId: ledgerAnchor.listings[0].listing_id,
    quantity: "0.1234567890",
    grossCash: "123.4500000000",
    fees: "0",
    taxes: "0.0000000001",
    tradeDate: "2026-01-13",
    settlementDate: "2026-01-15",
    sourceRecordId: "trade-1",
  };
}

it.each(["BUY", "SELL"] as const)(
  "round-trips %s and cash with exact decimal and evidence text",
  (kind) => {
    const input = buildSettledActivityReview(ledgerAnchor, base, cutoff, [
      record(),
      trade(kind),
    ]);
    const packet = JSON.parse(input.text);
    expect(packet.activity[1]).toMatchObject({
      kind,
      quantity: "0.1234567890",
      gross_cash: "123.4500000000",
      fees: "0",
      taxes: "0.0000000001",
      listing_id: ledgerAnchor.listings[0].listing_id,
    });
    expect(packet.activity[1]).not.toHaveProperty("amount");
    const restored = restoreSettledActivityReview(ledgerAnchor, input.text);
    expect(restored.entries).toEqual([record(), trade(kind)]);
    expect(
      buildSettledActivityReview(
        ledgerAnchor,
        restored.base,
        restored.cutoff,
        restored.entries,
      ).text,
    ).toBe(input.text);
    packet.activity[1].fees = 0;
    expect(() =>
      restoreSettledActivityReview(ledgerAnchor, JSON.stringify(packet)),
    ).toThrow(/cannot be edited/);
  },
);

it.each([
  { listingId: "unrelated" },
  { currency: "EUR" },
  { quantity: "0" },
  { quantity: "1e3" },
  { grossCash: "" },
  { fees: "" },
  { taxes: undefined },
  { tradeDate: "" },
  { settlementDate: "" },
  { amount: "1" },
])("rejects ambiguous trade details %j", (change) => {
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, base, cutoff, [
      { ...trade(), ...change },
    ]),
  ).toThrow();
});

function dividend(): SettledActivityDraft {
  return {
    ...record(),
    kind: "DIVIDEND",
    amount: "",
    listingId: ledgerAnchor.listings[0].listing_id,
    currency: "EUR",
    grossCash: "1.2500000000",
    fees: "0",
    taxes: "0.1500000000",
    sourceRecordId: "dividend",
  };
}

it("preserves a dividend received in a currency different from the listing and round-trips its evidence", () => {
  const original = buildSettledActivityReview(ledgerAnchor, base, cutoff, [
    dividend(),
  ]);
  const item = JSON.parse(original.text).activity[0];
  expect(item).toMatchObject({
    kind: "DIVIDEND",
    currency: "EUR",
    gross_cash: "1.2500000000",
    fees: "0",
    taxes: "0.1500000000",
  });
  expect(item).not.toHaveProperty("quantity");
  const restored = restoreSettledActivityReview(ledgerAnchor, original.text);
  expect(restored.entries).toEqual([dividend()]);
  expect(
    buildSettledActivityReview(
      ledgerAnchor,
      restored.base,
      restored.cutoff,
      restored.entries,
    ).text,
  ).toBe(original.text);
  item.taxes = 0;
  const changed = JSON.parse(original.text);
  changed.activity[0] = item;
  expect(() =>
    restoreSettledActivityReview(ledgerAnchor, JSON.stringify(changed)),
  ).toThrow(/cannot be edited/);
});

it.each([
  { listingId: "unknown" },
  { grossCash: "0" },
  { fees: "" },
  { taxes: undefined },
  { currency: "eur" },
  { quantity: "1" },
  { tradeDate: "2026-01-01" },
  { amount: "1" },
])("rejects incomplete or conflicting dividend evidence %j", (change) => {
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, base, cutoff, [
      { ...dividend(), ...change },
    ]),
  ).toThrow();
});
