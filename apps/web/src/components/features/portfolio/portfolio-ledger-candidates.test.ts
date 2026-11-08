import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/research/[...path]/route";
import {
  isLedgerCandidate,
  isLedgerCandidates,
  type LedgerCandidate,
} from "@/lib/domain-contracts";
import {
  ledgerPacket,
  ledgerReport,
  ledgerPortfolioId,
} from "../../../../e2e/fixtures/ledger";
import { inspectLedgerFile, ledgerStageBody } from "./portfolio-ledger-data";

const candidateId = "99999999-9999-4999-8999-999999999999";
function fixture(): LedgerCandidate {
  const preview = ledgerReport();
  const value = {
    id: candidateId,
    portfolio_id: ledgerPortfolioId,
    anchor_snapshot_id: preview.anchor_snapshot_id,
    base_candidate_id: null,
    input_sha256: preview.input_sha256,
    packet_sha256: "e".repeat(64),
    preview_sha256: "f".repeat(64),
    status: "PENDING",
    preview_status: preview.status,
    as_of: preview.as_of,
    reason: "Synthetic source review",
    submitted_by: "LOCAL_USER",
    submitted_at: preview.as_of,
    review: null,
    packet: ledgerPacket(),
    preview,
    changes: {
      added_activity_ids: [],
      changed_activity_ids: [],
      removed_activity_ids: [],
      opening_changed: false,
    },
    replayed: false,
  };
  if (!isLedgerCandidate(value))
    throw new Error("Invalid synthetic candidate fixture");
  return value;
}

it("validates source-bound dividend and tax records only in explicit v2 packets", () => {
  const row = fixture();
  row.packet.contract_version = "portfolio-ledger-preview-v2";
  row.preview.contract_version = "portfolio-ledger-preview-v2";
  row.preview.projection_version = "settled-booking-v2";
  row.packet.activity = [
    {
      id: candidateId,
      account_id: row.packet.accounts[0].account_id,
      kind: "DIVIDEND",
      sequence: 1,
      effective_at: row.as_of,
      listing_id: row.preview.consumed_listings[0].listing_id,
      currency: "EUR",
      gross_cash: "12.3456789012",
      fees: "0.1",
      taxes: "2.3456789012",
      evidence: { source_sha256: "a".repeat(64), source_record_id: "dividend" },
    },
    {
      id: "88888888-8888-4888-8888-888888888888",
      account_id: row.packet.accounts[0].account_id,
      kind: "TAX",
      sequence: 2,
      effective_at: row.as_of,
      currency: "EUR",
      amount: "0.9",
      evidence: { source_sha256: "a".repeat(64), source_record_id: "tax" },
    },
  ];
  row.preview.activity_count = 2;
  expect(isLedgerCandidate(row)).toBe(true);
  const missingIdentity = structuredClone(row);
  Object.assign(missingIdentity.packet.activity[0], {
    listing_id: candidateId,
  });
  expect(isLedgerCandidate(missingIdentity)).toBe(false);
  const imprecise = structuredClone(row);
  Object.assign(imprecise.packet.activity[0], { gross_cash: 12.345 });
  expect(isLedgerCandidate(imprecise)).toBe(false);
  const missingCharge = structuredClone(row);
  delete (missingCharge.packet.activity[0] as Partial<{ taxes: string }>).taxes;
  expect(isLedgerCandidate(missingCharge)).toBe(false);
  row.packet.contract_version = "portfolio-ledger-preview-v1";
  row.preview.contract_version = "portfolio-ledger-preview-v1";
  row.preview.projection_version = "settled-booking-v1";
  expect(isLedgerCandidate(row)).toBe(false);
  row.packet.activity.shift();
  row.preview.activity_count = 1;
  expect(isLedgerCandidate(row)).toBe(false);
});

it("validates paired internal transfers and retains both evidence records", () => {
  const row = fixture();
  const destination = "88888888-8888-4888-8888-888888888888";
  row.packet.contract_version = "portfolio-ledger-preview-v2";
  row.preview.contract_version = "portfolio-ledger-preview-v2";
  row.preview.projection_version = "settled-booking-v2";
  row.packet.accounts.push({
    ...structuredClone(row.packet.accounts[0]),
    account_id: destination,
    name: "Synthetic recipient",
    evidence: {
      source_sha256: "b".repeat(64),
      source_record_id: "recipient-opening",
    },
    positions: [],
    cash: [{ currency: "USD", balance: "0" }],
  });
  row.packet.activity = [
    {
      id: candidateId,
      account_id: row.packet.accounts[0].account_id,
      kind: "CASH_TRANSFER",
      sequence: 1,
      effective_at: row.as_of,
      currency: "USD",
      amount: "12.3400000000",
      evidence: { source_sha256: "a".repeat(64), source_record_id: "debit" },
      destination: {
        account_id: destination,
        currency: "USD",
        amount: "12.34",
        effective_at: row.as_of,
        evidence: {
          source_sha256: "b".repeat(64),
          source_record_id: "receipt",
        },
      },
    },
  ];
  row.preview.activity_count = 1;
  expect(isLedgerCandidate(row)).toBe(true);
  const text = JSON.stringify(row.packet);
  const file = inspectLedgerFile(text, "paired-transfer.json");
  expect(file.text).toBe(text);
  expect(file.evidence.find((e) => e.role === "Transfer receipt")).toEqual({
    role: "Transfer receipt",
    accountId: destination,
    reference: "receipt",
    sha256: "b".repeat(64),
  });
  for (const replacement of [
    { account_id: candidateId },
    { amount: 12.34 },
    { effective_at: "2026-01-03T00:00:00Z" },
    { currency: "EUR" },
    { evidence: null },
  ]) {
    const invalid = structuredClone(row);
    Object.assign(
      (invalid.packet.activity[0] as { destination: object }).destination,
      replacement,
    );
    expect(isLedgerCandidate(invalid)).toBe(false);
  }
  row.packet.contract_version = "portfolio-ledger-preview-v1";
  row.preview.contract_version = "portfolio-ledger-preview-v1";
  row.preview.projection_version = "settled-booking-v1";
  expect(isLedgerCandidate(row)).toBe(false);
});

it("validates security transfer identity, both quantity legs and explicit unavailable basis", () => {
  const row = fixture();
  const destination = "88888888-8888-4888-8888-888888888888";
  row.packet.contract_version = "portfolio-ledger-preview-v2";
  row.preview.contract_version = "portfolio-ledger-preview-v2";
  row.preview.projection_version = "settled-booking-v2";
  row.packet.accounts.push({
    ...structuredClone(row.packet.accounts[0]),
    account_id: destination,
    name: "Synthetic receiving account",
    positions: [],
    cash: [],
    evidence: {
      source_sha256: "b".repeat(64),
      source_record_id: "receiving-opening",
    },
  });
  row.packet.activity = [
    {
      id: candidateId,
      account_id: row.packet.accounts[0].account_id,
      kind: "SECURITY_TRANSFER",
      sequence: 1,
      effective_at: row.as_of,
      listing_id: row.preview.consumed_listings[0].listing_id,
      quantity: "1.2500000000",
      basis_status: "UNAVAILABLE",
      evidence: { source_sha256: "a".repeat(64), source_record_id: "sent" },
      destination: {
        account_id: destination,
        listing_id: row.preview.consumed_listings[0].listing_id,
        quantity: "1.25",
        effective_at: row.as_of,
        evidence: {
          source_sha256: "b".repeat(64),
          source_record_id: "received",
        },
      },
    },
  ];
  row.preview.activity_count = 1;
  expect(isLedgerCandidate(row)).toBe(true);
  const file = inspectLedgerFile(
    JSON.stringify(row.packet),
    "security-transfer.json",
  );
  expect(
    file.evidence.find((e) => e.role === "Transfer receipt")?.reference,
  ).toBe("received");
  for (const replacement of [
    { listing_id: candidateId },
    { account_id: candidateId },
    { quantity: 1.25 },
    { effective_at: "2026-01-03T00:00:00Z" },
    { evidence: null },
  ]) {
    const invalid = structuredClone(row);
    Object.assign(
      (invalid.packet.activity[0] as { destination: object }).destination,
      replacement,
    );
    expect(isLedgerCandidate(invalid)).toBe(false);
  }
  const fabricatedBasis = structuredClone(row);
  Object.assign(fabricatedBasis.packet.activity[0], { basis_status: "KNOWN" });
  expect(isLedgerCandidate(fabricatedBasis)).toBe(false);
  row.packet.contract_version = "portfolio-ledger-preview-v1";
  row.preview.contract_version = "portfolio-ledger-preview-v1";
  row.preview.projection_version = "settled-booking-v1";
  expect(isLedgerCandidate(row)).toBe(false);
});
beforeEach(() => {
  vi.stubEnv("NODE_ENV", "test");
  vi.stubEnv("API_BASE_URL", "http://127.0.0.1:8000");
  vi.stubEnv("WEB_ACCESS_USERNAME", "");
  vi.stubEnv("WEB_ACCESS_PASSWORD", "");
  vi.stubEnv("API_ACCESS_TOKEN", "synthetic-secret-token");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
it("preserves raw exact financial literals when wrapping a stage request", () => {
  const text = JSON.stringify(ledgerPacket()).replace(
    '"2.5000000000"',
    "9007199254740993",
  );
  const body = ledgerStageBody(
    inspectLedgerFile(text, "private.json"),
    candidateId,
    null,
    "a".repeat(64),
    'Reviewed "source"',
  );
  expect(body).toContain('"quantity":9007199254740993');
  expect(body).toContain('"proposal":' + text);
  expect(JSON.parse(body).reason).toBe('Reviewed "source"');
});
it("checks saved packet, preview and history scope", () => {
  const row = fixture();
  expect(isLedgerCandidate(row)).toBe(true);
  expect(
    isLedgerCandidates({
      portfolio_id: ledgerPortfolioId,
      current_accepted_candidate_id: null,
      current_revision_number: 0,
      candidates: [row],
    }),
  ).toBe(true);
  expect(
    isLedgerCandidates({
      portfolio_id: ledgerPortfolioId,
      current_accepted_candidate_id: null,
      current_revision_number: 1,
      candidates: [row],
    }),
  ).toBe(false);
  expect(
    isLedgerCandidates({
      portfolio_id: ledgerPortfolioId,
      current_accepted_candidate_id: null,
      current_revision_number: 0,
      candidates: [row, row],
    }),
  ).toBe(false);
});
it.each(["hash", "base", "status", "decimal", "changes", "actor", "packet"])(
  "rejects unverifiable saved candidate %s",
  (kind) => {
    const row = structuredClone(fixture());
    if (kind === "hash") row.preview.input_sha256 = "a".repeat(64);
    if (kind === "base") row.base_candidate_id = "bad";
    if (kind === "status") row.status = "ACCEPTED";
    if (kind === "decimal")
      Object.assign(row.packet.accounts[0].cash[0], { balance: 0 });
    if (kind === "changes")
      row.changes.changed_activity_ids = [candidateId, candidateId];
    if (kind === "actor") Object.assign(row, { submitted_by: "AGENT" });
    if (kind === "packet") row.packet.anchor_sha256 = "b".repeat(64);
    expect(isLedgerCandidate(row)).toBe(false);
  },
);
it("binds accepted receipt to its reviewed hashes and affirmative evidence", () => {
  const row = fixture();
  row.status = "ACCEPTED";
  row.review = {
    id: candidateId,
    decision: "ACCEPT",
    revision_number: 1,
    reviewed_by: "LOCAL_USER",
    reviewed_at: row.as_of,
    command: {
      decision: "ACCEPT",
      expected_base_candidate_id: null,
      expected_input_sha256: row.input_sha256,
      expected_preview_sha256: row.preview_sha256,
      reason: "Synthetic acceptance",
      source_evidence_reviewed: true,
      account_allocation_reviewed: true,
      settled_balance_basis_reviewed: true,
      full_replacement_reviewed: true,
      acknowledged_changed_activity_ids: [],
      acknowledged_removed_activity_ids: [],
    },
  };
  expect(isLedgerCandidate(row)).toBe(true);
  row.review.command.expected_preview_sha256 = "a".repeat(64);
  expect(isLedgerCandidate(row)).toBe(false);
});
it.each(["list", "detail", "stage", "review"])(
  "forwards only scoped %s ledger routes with server-only authentication",
  async (kind) => {
    const row = fixture();
    const path = ["portfolios", ledgerPortfolioId, "ledger", "candidates"];
    if (kind === "detail" || kind === "review") path.push(candidateId);
    if (kind === "review") path.push("review");
    const reply =
      kind === "list"
        ? {
            portfolio_id: ledgerPortfolioId,
            current_accepted_candidate_id: null,
            current_revision_number: 0,
            candidates: [row],
          }
        : row;
    const mock = vi.fn().mockResolvedValue(Response.json(reply));
    vi.stubGlobal("fetch", mock);
    const write = kind === "stage" || kind === "review";
    const response = await (write ? POST : GET)(
      new Request(`http://localhost/api/research/${path.join("/")}`, {
        method: write ? "POST" : "GET",
        ...(write
          ? {
              headers: { Origin: "http://localhost" },
              body: '{"exact":9007199254740993}',
            }
          : {}),
      }),
      { params: Promise.resolve({ path }) },
    );
    expect(response.status).toBe(200);
    expect(mock.mock.calls[0][1].headers["X-API-Access-Token"]).toBe(
      "synthetic-secret-token",
    );
    if (write)
      expect(mock.mock.calls[0][1].body).toBe('{"exact":9007199254740993}');
    expect(JSON.stringify(await response.json())).not.toContain(
      "synthetic-secret-token",
    );
  },
);
it("rejects cross-origin stage before contacting the backend", async () => {
  const mock = vi.fn();
  vi.stubGlobal("fetch", mock);
  const path = ["portfolios", ledgerPortfolioId, "ledger", "candidates"];
  const result = await POST(
    new Request("http://localhost/api/research/" + path.join("/"), {
      method: "POST",
      headers: { Origin: "https://external.example" },
      body: "{}",
    }),
    { params: Promise.resolve({ path }) },
  );
  expect(result.status).toBe(403);
  expect(mock).not.toHaveBeenCalled();
});
it("preserves server authorization failures and rejects mismatched response scope", async () => {
  const path = ["portfolios", ledgerPortfolioId, "ledger", "candidates"];
  const mock = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json({ detail: "private" }, { status: 403 }),
    )
    .mockResolvedValueOnce(
      Response.json({ ...fixture(), portfolio_id: candidateId }),
    );
  vi.stubGlobal("fetch", mock);
  const call = () =>
    POST(
      new Request("http://localhost/api/research/" + path.join("/"), {
        method: "POST",
        body: "{}",
      }),
      { params: Promise.resolve({ path }) },
    );
  const forbidden = await call();
  expect(forbidden.status).toBe(403);
  expect(await forbidden.text()).not.toContain("private");
  expect((await call()).status).toBe(503);
});

it.each(["missing-activity", "phantom-change", "contradictory-current"])(
  "rejects inconsistent correction/history %s",
  (kind) => {
    const row = fixture();
    if (kind === "missing-activity") {
      row.preview.activity_count = 1;
      expect(isLedgerCandidate(row)).toBe(false);
    }
    if (kind === "phantom-change") {
      row.changes.changed_activity_ids = [candidateId];
      expect(isLedgerCandidate(row)).toBe(false);
    }
    if (kind === "contradictory-current")
      expect(
        isLedgerCandidates({
          portfolio_id: ledgerPortfolioId,
          current_accepted_candidate_id: row.id,
          current_revision_number: 1,
          candidates: [row],
        }),
      ).toBe(false);
  },
);
