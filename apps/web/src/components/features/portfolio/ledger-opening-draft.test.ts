import { createHash } from "node:crypto";
import { expect, it } from "vitest";
import { ledgerAnchor, ledgerAccountId } from "../../../../e2e/fixtures/ledger";
import {
  buildOpeningReview,
  hashOpeningStatement,
  statementFileLimit,
  type OpeningAccountDraft,
} from "./ledger-opening-draft";

function account(): OpeningAccountDraft {
  return {
    id: ledgerAccountId,
    name: "Synthetic account",
    kind: "BROKERAGE",
    brokerName: "Synthetic broker",
    sourceSha256: "b".repeat(64),
    sourceRecordId: "opening-1",
    hashing: false,
    positions: [
      {
        id: "position",
        listingId: ledgerAnchor.listings[0].listing_id,
        quantity: "2.5000000000",
      },
    ],
    cash: [{ id: "cash", currency: "USD", balance: "100.0000000000" }],
  };
}

it("binds exact source text and a companyless ETF to the current opening anchor", () => {
  const draft = account();
  draft.positions[0].quantity = "9007199254740993.1234567890";
  draft.cash.push({ id: "euro", currency: "EUR", balance: "0" });
  const file = buildOpeningReview(ledgerAnchor, [draft], true);
  const packet = JSON.parse(file.text);
  expect(packet).toEqual({
    contract_version: "portfolio-ledger-preview-v2",
    anchor_snapshot_id: ledgerAnchor.snapshot.id,
    anchor_sha256: ledgerAnchor.anchor_sha256,
    as_of: ledgerAnchor.snapshot.effective_at,
    accounts: [
      {
        account_id: draft.id,
        name: draft.name,
        kind: draft.kind,
        broker_name: draft.brokerName,
        evidence: {
          source_sha256: draft.sourceSha256,
          source_record_id: draft.sourceRecordId,
        },
        positions: [
          {
            listing_id: ledgerAnchor.listings[0].listing_id,
            quantity: "9007199254740993.1234567890",
          },
        ],
        cash: [
          { currency: "USD", balance: "100.0000000000" },
          { currency: "EUR", balance: "0" },
        ],
      },
    ],
    activity: [],
    ending_statement: null,
  });
  expect(ledgerAnchor.listings[0].company_id).toBeNull();
  expect(file.evidence).toHaveLength(1);
  expect(buildOpeningReview(ledgerAnchor, [draft], true).text).toBe(file.text);
});

it("requires a source-date acknowledgement and explicit account evidence", () => {
  expect(() => buildOpeningReview(ledgerAnchor, [account()], false)).toThrow(
    /anchor date/,
  );
  expect(() => buildOpeningReview(ledgerAnchor, [], true)).toThrow(
    /one and 20/,
  );
  for (const change of [
    { name: " " },
    { brokerName: "" },
    { id: "bad" },
    { sourceSha256: "" },
    { sourceRecordId: " " },
    { hashing: true },
  ]) {
    expect(() =>
      buildOpeningReview(ledgerAnchor, [{ ...account(), ...change }], true),
    ).toThrow();
  }
});

it("preserves an explicitly unallocated opening without inventing a broker", () => {
  const draft = {
    ...account(),
    kind: "UNALLOCATED_OPENING" as const,
    brokerName: "",
  };
  expect(
    JSON.parse(buildOpeningReview(ledgerAnchor, [draft], true).text).accounts[0]
      .broker_name,
  ).toBeNull();
  expect(() =>
    buildOpeningReview(
      ledgerAnchor,
      [{ ...draft, brokerName: "Invented" }],
      true,
    ),
  ).toThrow(/conflicting/);
});

it.each([
  "",
  " ",
  "-1",
  "NaN",
  "Infinity",
  "1e2",
  "1,2",
  "01",
  "1.12345678901",
  "1000000000000000000",
])("rejects ambiguous or unsupported decimal input %j", (value) => {
  const position = account();
  position.positions[0].quantity = value;
  expect(() => buildOpeningReview(ledgerAnchor, [position], true)).toThrow(
    /decimal/,
  );
  const cash = account();
  cash.cash[0].balance = value;
  expect(() => buildOpeningReview(ledgerAnchor, [cash], true)).toThrow(
    /decimal/,
  );
});

it("retains explicit zero while rejecting duplicate or unrelated source rows", () => {
  const draft = account();
  draft.positions[0].quantity = "0";
  draft.cash[0].balance = "0.0000000000";
  expect(buildOpeningReview(ledgerAnchor, [draft], true).text).toContain(
    '"balance":"0.0000000000"',
  );
  draft.positions.push({ ...draft.positions[0], id: "duplicate" });
  expect(() => buildOpeningReview(ledgerAnchor, [draft], true)).toThrow(
    /duplicate listing/,
  );
  draft.positions.pop();
  draft.cash.push({ ...draft.cash[0], id: "duplicate" });
  expect(() => buildOpeningReview(ledgerAnchor, [draft], true)).toThrow(
    /duplicate cash/,
  );
  draft.cash.pop();
  draft.positions[0].listingId = "unrelated";
  expect(() => buildOpeningReview(ledgerAnchor, [draft], true)).toThrow(
    /exact listing/,
  );
});

it("rejects duplicate account identity, duplicate evidence and noncanonical currency", () => {
  expect(() =>
    buildOpeningReview(ledgerAnchor, [account(), account()], true),
  ).toThrow(/own identity/);
  const second = { ...account(), id: "66666666-6666-4666-8666-666666666666" };
  expect(() =>
    buildOpeningReview(ledgerAnchor, [account(), second], true),
  ).toThrow(/one account/);
  const draft = account();
  draft.cash[0].currency = "eur";
  expect(() => buildOpeningReview(ledgerAnchor, [draft], true)).toThrow(
    /currency/,
  );
});

it("enforces native opening size limits before submission", () => {
  expect(() =>
    buildOpeningReview(ledgerAnchor, Array(21).fill(account()), true),
  ).toThrow(/20/);
  const draft = account();
  draft.positions = Array(1001).fill(draft.positions[0]);
  expect(() => buildOpeningReview(ledgerAnchor, [draft], true)).toThrow(
    /1,000/,
  );
  draft.positions = [];
  draft.cash = Array(101).fill(draft.cash[0]);
  expect(() => buildOpeningReview(ledgerAnchor, [draft], true)).toThrow(
    /100 cash/,
  );
});

it("hashes the original statement bytes locally with a bounded size", async () => {
  const bytes = new Uint8Array([0, 255, 12, 47]);
  const statement = new File([bytes], "synthetic.bin");
  await expect(hashOpeningStatement(statement)).resolves.toBe(
    createHash("sha256").update(bytes).digest("hex"),
  );
  await expect(hashOpeningStatement(new File([], "empty"))).rejects.toThrow(
    /nonempty/,
  );
  const oversized = { size: statementFileLimit + 1 } as File;
  await expect(hashOpeningStatement(oversized)).rejects.toThrow(/10 MiB/);
});
