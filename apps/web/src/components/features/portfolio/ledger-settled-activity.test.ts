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

const destinationId = "88888888-8888-4888-8888-888888888888";
const transferBase = buildOpeningReview(
  ledgerAnchor,
  [
    opening,
    {
      ...opening,
      id: destinationId,
      name: "Second synthetic account",
      sourceRecordId: "second-opening",
      positions: [],
      cash: [],
    },
  ],
  true,
);
function transfer(): SettledActivityDraft {
  return {
    ...record(),
    kind: "CASH_TRANSFER",
    amount: "10.0000000000",
    sourceRecordId: "debit",
    destinationAccountId: destinationId,
    destinationCurrency: "USD",
    destinationAmount: "10.0000000000",
    destinationEffectiveAt: "2026-01-15T09:30:00Z",
    destinationSourceSha256: "d".repeat(64),
    destinationSourceRecordId: "credit",
  };
}
it("round-trips independently evidenced paired cash transfer legs without losing precision", () => {
  const original = buildSettledActivityReview(
    ledgerAnchor,
    transferBase,
    cutoff,
    [transfer()],
  );
  const activity = JSON.parse(original.text).activity[0];
  expect(activity.destination).toEqual({
    account_id: destinationId,
    currency: "USD",
    amount: "10.0000000000",
    effective_at: "2026-01-15T09:30:00Z",
    evidence: { source_sha256: "d".repeat(64), source_record_id: "credit" },
  });
  expect(original.evidence).toHaveLength(4);
  const session = restoreSettledActivityReview(ledgerAnchor, original.text);
  expect(session.entries).toEqual([transfer()]);
  expect(
    buildSettledActivityReview(
      ledgerAnchor,
      session.base,
      session.cutoff,
      session.entries,
    ).text,
  ).toBe(original.text);
  activity.destination.amount = 10;
  const altered = JSON.parse(original.text);
  altered.activity[0] = activity;
  expect(() =>
    restoreSettledActivityReview(ledgerAnchor, JSON.stringify(altered)),
  ).toThrow(/cannot be edited/);
});
it.each([
  { destinationAccountId: ledgerAccountId },
  { destinationAccountId: "missing" },
  { destinationAmount: "0" },
  { destinationCurrency: "usd" },
  { destinationEffectiveAt: "2026-01-15T09:30:00" },
  { destinationSourceSha256: "" },
  { destinationSourceRecordId: "" },
  {
    destinationSourceSha256: "c".repeat(64),
    destinationSourceRecordId: "debit",
  },
])("rejects incomplete or duplicate destination evidence %j", (change) => {
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, transferBase, cutoff, [
      { ...transfer(), ...change },
    ]),
  ).toThrow();
});

it("rejects a destination receipt reused by a later activity", () => {
  const reused: SettledActivityDraft = {
    ...record(),
    id: "99999999-9999-4999-8999-999999999999",
    sequence: "2",
    sourceSha256: "d".repeat(64),
    sourceRecordId: "credit",
  };
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, transferBase, cutoff, [
      transfer(),
      reused,
    ]),
  ).toThrow(/duplicates/);
});

function securityTransfer(): SettledActivityDraft {
  return {
    ...record(),
    kind: "SECURITY_TRANSFER",
    currency: "",
    amount: "",
    listingId: ledgerAnchor.listings[0].listing_id,
    quantity: "0.5000000000",
    basisUnavailable: true,
    sourceRecordId: "security-debit",
    destinationAccountId: destinationId,
    destinationListingId: ledgerAnchor.listings[0].listing_id,
    destinationQuantity: "0.5000000000",
    destinationEffectiveAt: "2026-01-15T09:30:00Z",
    destinationSourceSha256: "d".repeat(64),
    destinationSourceRecordId: "security-credit",
  };
}
it("preserves independently evidenced security transfer legs and explicit unavailable basis", () => {
  const original = buildSettledActivityReview(
    ledgerAnchor,
    transferBase,
    cutoff,
    [securityTransfer()],
  );
  const row = JSON.parse(original.text).activity[0];
  expect(row).toMatchObject({
    kind: "SECURITY_TRANSFER",
    basis_status: "UNAVAILABLE",
    quantity: "0.5000000000",
    destination: {
      listing_id: ledgerAnchor.listings[0].listing_id,
      quantity: "0.5000000000",
      evidence: { source_record_id: "security-credit" },
    },
  });
  expect(row).not.toHaveProperty("currency");
  expect(row).not.toHaveProperty("amount");
  const restored = restoreSettledActivityReview(ledgerAnchor, original.text);
  expect(restored.entries).toEqual([securityTransfer()]);
  expect(
    buildSettledActivityReview(
      ledgerAnchor,
      restored.base,
      restored.cutoff,
      restored.entries,
    ).text,
  ).toBe(original.text);
  row.destination.quantity = 0.5;
  const invalid = JSON.parse(original.text);
  invalid.activity[0] = row;
  expect(() =>
    restoreSettledActivityReview(ledgerAnchor, JSON.stringify(invalid)),
  ).toThrow(/cannot be edited/);
});
it.each([
  { basisUnavailable: false },
  { listingId: "unknown" },
  { quantity: "0" },
  { destinationListingId: "unknown" },
  { destinationQuantity: "" },
  { destinationAccountId: ledgerAccountId },
  { destinationSourceRecordId: "" },
  { amount: "1" },
  { currency: "USD" },
  { destinationCurrency: "USD" },
  { fees: "0" },
])(
  "rejects incomplete or unrepresentable security transfer evidence %j",
  (change) => {
    expect(() =>
      buildSettledActivityReview(ledgerAnchor, transferBase, cutoff, [
        { ...securityTransfer(), ...change },
      ]),
    ).toThrow();
  },
);

it("uses a separately verified non-anchor listing without mutating the anchor and restores its exact packet", () => {
  const extra = {
    ...ledgerAnchor.listings[0],
    listing_id: "99999999-9999-4999-8999-999999999999",
    ticker: "OTHER",
    venue: "NYSE",
  };
  const entry = { ...trade(), listingId: extra.listing_id };
  expect(() =>
    buildSettledActivityReview(ledgerAnchor, base, cutoff, [entry]),
  ).toThrow();
  const file = buildSettledActivityReview(
    ledgerAnchor,
    base,
    cutoff,
    [entry],
    [extra],
  );
  expect(ledgerAnchor.listings).toHaveLength(1);
  expect(
    restoreSettledActivityReview(ledgerAnchor, file.text, [extra]).entries,
  ).toEqual([entry]);
  expect(() => restoreSettledActivityReview(ledgerAnchor, file.text)).toThrow();
});
