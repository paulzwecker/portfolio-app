import { expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ledgerAnchor, ledgerAccountId } from "../../../../e2e/fixtures/ledger";
import {
  buildOpeningReview,
  type OpeningAccountDraft,
} from "./ledger-opening-draft";
import {
  buildSettledActivityReview,
  type SettledActivityDraft,
} from "./ledger-settled-activity";
import {
  buildEndingReview,
  endingOpeningAccounts,
  restoreEndingReview,
  type EndingAccountDraft,
} from "./ledger-ending-draft";
import { LedgerEndingBuilder } from "./ledger-ending-builder";

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
      id: "p",
      listingId: ledgerAnchor.listings[0].listing_id,
      quantity: "2.5",
    },
  ],
  cash: [
    { id: "c", currency: "USD", balance: "100" },
    { id: "z", currency: "EUR", balance: "0" },
  ],
};
const base = buildOpeningReview(ledgerAnchor, [opening], true);
const activity: SettledActivityDraft = {
  id: "66666666-6666-4666-8666-666666666666",
  accountId: ledgerAccountId,
  kind: "DEPOSIT",
  sequence: "1",
  effectiveAt: "2026-01-15T10:30:00+01:00",
  currency: "USD",
  amount: "1.2500000000",
  sourceSha256: "c".repeat(64),
  sourceRecordId: "deposit",
};
const cashBase = buildSettledActivityReview(
  ledgerAnchor,
  base,
  "2026-01-31T23:59:59+01:00",
  [activity],
);
function ending(): EndingAccountDraft {
  return {
    accountId: ledgerAccountId,
    sourceSha256: "d".repeat(64),
    sourceRecordId: "ending",
    positions: [
      {
        id: "p",
        listingId: ledgerAnchor.listings[0].listing_id,
        quantity: "9007199254740993.1234567890",
      },
    ],
    cash: [
      { id: "c", currency: "USD", balance: "101.2500000000" },
      { id: "z", currency: "EUR", balance: "0" },
    ],
  };
}

it("restores ending evidence, exact zero and high precision without changing the packet", () => {
  const draft = ending();
  const original = buildEndingReview(ledgerAnchor, cashBase, [draft], true);
  const restored = restoreEndingReview(ledgerAnchor, original.text);
  expect(restored.file.text).toBe(cashBase.text);
  expect(restored.opening[0].id).toBe(ledgerAccountId);
  expect(restored.accounts[0]).toMatchObject({
    accountId: ledgerAccountId,
    sourceSha256: draft.sourceSha256,
    sourceRecordId: draft.sourceRecordId,
    positions: [
      {
        listingId: draft.positions[0].listingId,
        quantity: "9007199254740993.1234567890",
      },
    ],
    cash: [
      { currency: "USD", balance: "101.2500000000" },
      { currency: "EUR", balance: "0" },
    ],
  });
  expect(
    buildEndingReview(ledgerAnchor, restored.file, restored.accounts, true)
      .text,
  ).toBe(original.text);
});

it("fails closed for stale, lossy, incomplete or unsupported ending packets", () => {
  const text = buildEndingReview(ledgerAnchor, cashBase, [ending()], true).text;
  type Packet = {
    ending_statement: {
      effective_at: string;
      accounts: {
        evidence: { source_sha256: string };
        positions: { quantity: string | number; extra?: string }[];
        cash: { currency: string; balance: string | number }[];
      }[];
    };
    activity: { kind: string }[];
  };
  const altered = (change: (value: Packet) => void) => {
    const value = JSON.parse(text) as Packet;
    change(value);
    return JSON.stringify(value);
  };
  for (const value of [
    "{bad",
    text + " ",
    altered((v) => {
      v.ending_statement.accounts[0].positions[0].quantity = 9007199254740992;
    }),
    altered((v) => {
      v.ending_statement.accounts[0].positions[0].extra = "source detail";
    }),
    altered((v) => {
      v.ending_statement.accounts[0].cash[0].balance = 0;
    }),
    altered((v) => {
      v.ending_statement.accounts = [];
    }),
    altered((v) => {
      v.ending_statement.effective_at = "2026-01-31T23:59:58+01:00";
    }),
    altered((v) => {
      v.activity[0].kind = "DIVIDEND";
    }),
  ])
    expect(() => restoreEndingReview(ledgerAnchor, value)).toThrow(
      /cannot be edited/,
    );
  expect(() =>
    restoreEndingReview(
      { ...ledgerAnchor, anchor_sha256: "f".repeat(64) },
      text,
    ),
  ).toThrow(/cannot be edited/);
});

it("labels reordered ending accounts by identity", () => {
  const other = {
    ...opening,
    id: "77777777-7777-4777-8777-777777777777",
    name: "Second account",
    sourceRecordId: "other-opening",
  };
  const multi = buildOpeningReview(ledgerAnchor, [opening, other], true);
  const second = {
    ...ending(),
    accountId: other.id,
    sourceRecordId: "other-ending",
  };
  const text = buildEndingReview(
    ledgerAnchor,
    multi,
    [second, ending()],
    true,
  ).text;
  const restored = restoreEndingReview(ledgerAnchor, text);
  const markup = renderToStaticMarkup(
    createElement(LedgerEndingBuilder, {
      anchor: ledgerAnchor,
      base: restored.file,
      opening: restored.opening,
      initialAccounts: restored.accounts,
      disabled: false,
      onChange: () => {},
      onReview: async () => {},
      onClose: () => {},
    }),
  );
  expect(markup).toContain("Ending account 1 · Second account");
  expect(markup).toContain("Ending account 2 · Synthetic account");
});

it("adds independently observed exact ending rows without changing opening, activity or cutoff", () => {
  const draft = ending();
  const result = buildEndingReview(ledgerAnchor, cashBase, [draft], true);
  const packet = JSON.parse(result.text);
  const original = JSON.parse(cashBase.text);
  expect(packet.accounts).toEqual(original.accounts);
  expect(packet.activity).toEqual(original.activity);
  expect(packet.as_of).toBe(original.as_of);
  expect(packet.ending_statement).toEqual({
    effective_at: original.as_of,
    accounts: [
      {
        account_id: ledgerAccountId,
        evidence: {
          source_sha256: draft.sourceSha256,
          source_record_id: "ending",
        },
        positions: [
          {
            listing_id: ledgerAnchor.listings[0].listing_id,
            quantity: "9007199254740993.1234567890",
          },
        ],
        cash: [
          { currency: "USD", balance: "101.2500000000" },
          { currency: "EUR", balance: "0" },
        ],
      },
    ],
  });
  expect(result.evidence).toHaveLength(3);
  expect(buildEndingReview(ledgerAnchor, cashBase, [draft], true).text).toBe(
    result.text,
  );
  expect(endingOpeningAccounts(ledgerAnchor, base)[0].id).toBe(ledgerAccountId);
});

it("requires complete account identity, evidence and cutoff acknowledgement", () => {
  expect(() =>
    buildEndingReview(ledgerAnchor, base, [ending()], false),
  ).toThrow(/cutoff/);
  expect(() => buildEndingReview(ledgerAnchor, base, [], true)).toThrow(
    /each opening/,
  );
  expect(() =>
    buildEndingReview(
      ledgerAnchor,
      base,
      [{ ...ending(), accountId: "other" }],
      true,
    ),
  ).toThrow(/each opening/);
  expect(() =>
    buildEndingReview(
      ledgerAnchor,
      base,
      [{ ...ending(), sourceSha256: "" }],
      true,
    ),
  ).toThrow(/source hash/);
  expect(() =>
    buildEndingReview(
      ledgerAnchor,
      base,
      [{ ...ending(), sourceRecordId: " " }],
      true,
    ),
  ).toThrow(/source hash/);
});

it("requires a unique ending source for each declared account", () => {
  const other = {
    ...opening,
    id: "77777777-7777-4777-8777-777777777777",
    sourceRecordId: "other-opening",
  };
  const multi = buildOpeningReview(ledgerAnchor, [opening, other], true);
  const first = ending();
  const second = { ...ending(), accountId: other.id };
  expect(() =>
    buildEndingReview(ledgerAnchor, multi, [first, second], true),
  ).toThrow(/duplicates another ending source/);
  second.sourceRecordId = "other-ending";
  const result = JSON.parse(
    buildEndingReview(ledgerAnchor, multi, [first, second], true).text,
  );
  expect(
    result.ending_statement.accounts.map(
      (item: { account_id: string }) => item.account_id,
    ),
  ).toEqual([opening.id, other.id]);
});

it("preserves empty and explicit zero observations while rejecting malformed or duplicate rows", () => {
  const draft = ending();
  draft.positions = [];
  draft.cash = [{ id: "zero", currency: "EUR", balance: "0" }];
  expect(buildEndingReview(ledgerAnchor, base, [draft], true).text).toContain(
    '"balance":"0"',
  );
  draft.cash[0].balance = "";
  expect(() => buildEndingReview(ledgerAnchor, base, [draft], true)).toThrow(
    /decimal cash/,
  );
  draft.cash[0].balance = "0";
  draft.cash.push({ ...draft.cash[0], id: "duplicate" });
  expect(() => buildEndingReview(ledgerAnchor, base, [draft], true)).toThrow(
    /duplicate/,
  );
  draft.cash = [];
  draft.positions = [{ id: "bad", listingId: "unknown", quantity: "0" }];
  expect(() => buildEndingReview(ledgerAnchor, base, [draft], true)).toThrow(
    /exact listing/,
  );
});

it("rejects stale or unsupported source packets without silently discarding their data", () => {
  expect(() =>
    buildEndingReview(
      { ...ledgerAnchor, anchor_sha256: "f".repeat(64) },
      cashBase,
      [ending()],
      true,
    ),
  ).toThrow();
  const packet = JSON.parse(cashBase.text);
  packet.activity[0].kind = "DIVIDEND";
  expect(() =>
    buildEndingReview(
      ledgerAnchor,
      { ...cashBase, text: JSON.stringify(packet) },
      [ending()],
      true,
    ),
  ).toThrow();
  const completed = buildEndingReview(ledgerAnchor, base, [ending()], true);
  expect(() =>
    buildEndingReview(ledgerAnchor, completed, [ending()], true),
  ).toThrow(/without an ending/);
});

it("retains mixed trade and cash evidence when independently recorded ending observations are restored", () => {
  const trade: SettledActivityDraft = {
    ...activity,
    id: "77777777-7777-4777-8777-777777777777",
    kind: "BUY",
    sequence: "2",
    amount: "",
    listingId: ledgerAnchor.listings[0].listing_id,
    quantity: "0.5000000000",
    grossCash: "10.00",
    fees: "0",
    taxes: "0.05",
    tradeDate: "2026-01-13",
    settlementDate: "2026-01-15",
    sourceRecordId: "buy",
  };
  const mixed = buildSettledActivityReview(
    ledgerAnchor,
    base,
    "2026-01-31T23:59:59+01:00",
    [activity, trade],
  );
  const original = buildEndingReview(ledgerAnchor, mixed, [ending()], true);
  const restored = restoreEndingReview(ledgerAnchor, original.text);
  expect(restored.file.text).toBe(mixed.text);
  expect(
    buildEndingReview(ledgerAnchor, restored.file, restored.accounts, true)
      .text,
  ).toBe(original.text);
});

it("retains dividend evidence through ending-statement restoration", () => {
  const income: SettledActivityDraft = {
    ...activity,
    kind: "DIVIDEND",
    amount: "",
    currency: "EUR",
    listingId: ledgerAnchor.listings[0].listing_id,
    grossCash: "1.2500000000",
    fees: "0",
    taxes: "0.1500000000",
    sourceRecordId: "dividend",
  };
  const incomeBase = buildSettledActivityReview(
    ledgerAnchor,
    base,
    "2026-01-31T23:59:59+01:00",
    [income],
  );
  const original = buildEndingReview(
    ledgerAnchor,
    incomeBase,
    [ending()],
    true,
  );
  const restored = restoreEndingReview(ledgerAnchor, original.text);
  expect(restored.file.text).toBe(incomeBase.text);
  expect(
    buildEndingReview(ledgerAnchor, restored.file, restored.accounts, true)
      .text,
  ).toBe(original.text);
});

it("restores ending statements with both independently evidenced cash transfer legs", () => {
  const receiving: OpeningAccountDraft = {
    ...opening,
    id: "88888888-8888-4888-8888-888888888888",
    name: "Receiving",
    sourceRecordId: "receiver-opening",
    positions: [],
    cash: [],
  };
  const openingFile = buildOpeningReview(
    ledgerAnchor,
    [opening, receiving],
    true,
  );
  const transfer: SettledActivityDraft = {
    ...activity,
    kind: "CASH_TRANSFER",
    amount: "10.00",
    sourceRecordId: "debit",
    destinationAccountId: receiving.id,
    destinationCurrency: "USD",
    destinationAmount: "10.00",
    destinationEffectiveAt: activity.effectiveAt,
    destinationSourceSha256: "e".repeat(64),
    destinationSourceRecordId: "credit",
  };
  const transferFile = buildSettledActivityReview(
    ledgerAnchor,
    openingFile,
    "2026-01-31T23:59:59+01:00",
    [transfer],
  );
  const endingAccounts = [
    ending(),
    {
      ...ending(),
      accountId: receiving.id,
      sourceRecordId: "receiver-ending",
      positions: [],
      cash: [],
    },
  ];
  const statement = buildEndingReview(
    ledgerAnchor,
    transferFile,
    endingAccounts,
    true,
  );
  const restored = restoreEndingReview(ledgerAnchor, statement.text);
  expect(restored.file.text).toBe(transferFile.text);
  expect(
    buildEndingReview(ledgerAnchor, restored.file, restored.accounts, true)
      .text,
  ).toBe(statement.text);
});
