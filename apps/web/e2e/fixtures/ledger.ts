import type {
  PortfolioLedgerAnchor,
  PortfolioLedgerPreview,
} from "../../src/lib/domain-contracts";

export const ledgerAccountId = "11111111-1111-4111-8111-111111111111";
export const ledgerPortfolioId = "33333333-3333-4333-8333-333333333333";
const listingId = "22222222-2222-4222-8222-222222222222";
const iso = "2026-01-01T00:00:00Z";

export const ledgerAnchor: PortfolioLedgerAnchor = {
  portfolio_id: ledgerPortfolioId,
  anchor_sha256: "a".repeat(64),
  snapshot: {
    id: "44444444-4444-4444-8444-444444444444",
    portfolio_id: ledgerPortfolioId,
    completeness: "COMPLETE",
    actor: "IMPORT",
    reason: "Synthetic ledger anchor",
    source: "synthetic-ledger-v1",
    effective_at: iso,
    recorded_at: iso,
    positions: [{ listing_id: listingId, quantity: "2.5000000000" }],
    cash_positions: [
      { currency: "USD", balance: "100.0000000000" },
      { currency: "EUR", balance: "0.0000000000" },
    ],
  },
  listings: [
    {
      listing_id: listingId,
      security_id: "55555555-5555-4555-8555-555555555555",
      company_id: null,
      ticker: "SYNF",
      venue: "XETRA",
      currency: "USD",
      security_type: "ETF",
      identity_source_ref: "synthetic-reviewed-listing",
    },
  ],
};

export function ledgerPacket(
  anchor = ledgerAnchor,
  asOf = "2026-01-02T00:00:00Z",
) {
  return {
    contract_version: "portfolio-ledger-preview-v1",
    anchor_snapshot_id: anchor.snapshot.id,
    anchor_sha256: anchor.anchor_sha256,
    as_of: asOf,
    accounts: [
      {
        account_id: ledgerAccountId,
        name: "Synthetic broker account",
        kind: "BROKERAGE",
        broker_name: "Synthetic Broker",
        evidence: {
          source_sha256: "b".repeat(64),
          source_record_id: "opening-account-1",
        },
        positions: anchor.snapshot.positions.map((row) => ({ ...row })),
        cash: anchor.snapshot.cash_positions.map((row) => ({ ...row })),
      },
    ],
    activity: [] as Record<string, unknown>[],
    ending_statement: {
      effective_at: asOf,
      accounts: [
        {
          account_id: ledgerAccountId,
          evidence: {
            source_sha256: "c".repeat(64),
            source_record_id: "ending-account-1",
          },
          positions: anchor.snapshot.positions.map((row) => ({ ...row })),
          cash: anchor.snapshot.cash_positions.map((row) => ({ ...row })),
        },
      ],
    },
  };
}

export function ledgerReport(): PortfolioLedgerPreview {
  const rows = [
    { domain: "POSITION" as const, key: listingId, amount: "2.5000000000" },
    { domain: "CASH" as const, key: "EUR", amount: "0.0000000000" },
    { domain: "CASH" as const, key: "USD", amount: "100.0000000000" },
  ];
  return {
    contract_version: "portfolio-ledger-preview-v1",
    projection_version: "settled-booking-v1",
    preview_only: true,
    status: "ENDING_RECONCILED",
    portfolio_id: ledgerPortfolioId,
    anchor_snapshot_id: ledgerAnchor.snapshot.id,
    anchor_sha256: ledgerAnchor.anchor_sha256,
    anchor_recorded_at: iso,
    input_sha256: "d".repeat(64),
    as_of: "2026-01-02T00:00:00Z",
    activity_count: 0,
    issues: [],
    consumed_listings: ledgerAnchor.listings,
    opening_reconciliation: rows.map((row) => ({
      domain: row.domain,
      key: row.key,
      observed: row.amount,
      opening: row.amount,
      difference: "0",
      status: "MATCH",
    })),
    positions: [{ listing_id: listingId, quantity: "2.5000000000" }],
    cash: ledgerAnchor.snapshot.cash_positions.map((row) => ({
      currency: row.currency,
      balance: row.balance!,
    })),
    accounts: [
      {
        account_id: ledgerAccountId,
        positions: [{ listing_id: listingId, quantity: "2.5000000000" }],
        cash: [
          { currency: "USD", balance: "100.0000000000" },
          { currency: "EUR", balance: "0.0000000000" },
        ],
      },
    ],
    ending_status: "MATCH",
    ending_statement_at: "2026-01-02T00:00:00Z",
    ending_reconciliation: [null, ledgerAccountId].flatMap((account_id) =>
      rows.map((row) => ({
        account_id,
        domain: row.domain,
        key: row.key,
        projected: row.amount,
        observed: row.amount,
        difference: "0",
        status: "MATCH" as const,
      })),
    ),
  };
}
