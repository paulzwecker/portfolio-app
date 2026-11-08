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
import {
  buildEndingReview,
  endingOpeningAccounts,
  type EndingAccountDraft,
} from "./ledger-ending-draft";

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
const activity: CashActivityDraft = {
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
const cashBase = buildCashActivityReview(
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
