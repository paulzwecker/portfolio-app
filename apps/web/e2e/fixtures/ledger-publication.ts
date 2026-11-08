import type { LedgerCandidate } from "../../src/lib/domain-contracts";
import type {
  LedgerPublication,
  LedgerPublicationPlan,
} from "../../src/lib/ledger-publication-contracts";
import { ledgerAnchor, ledgerPacket, ledgerReport } from "./ledger";

export function acceptedLedgerCandidate(): LedgerCandidate {
  const preview = ledgerReport();
  const id = "99999999-9999-4999-8999-999999999999";
  return {
    id,
    portfolio_id: preview.portfolio_id,
    anchor_snapshot_id: preview.anchor_snapshot_id,
    base_candidate_id: null,
    input_sha256: preview.input_sha256,
    packet_sha256: "e".repeat(64),
    preview_sha256: "f".repeat(64),
    status: "ACCEPTED",
    preview_status: "ENDING_RECONCILED",
    as_of: preview.as_of,
    reason: "Synthetic source review",
    submitted_by: "LOCAL_USER",
    submitted_at: preview.as_of,
    review: {
      id: "88888888-8888-4888-8888-888888888888",
      decision: "ACCEPT",
      revision_number: 1,
      reviewed_by: "LOCAL_USER",
      reviewed_at: preview.as_of,
      command: {
        decision: "ACCEPT",
        expected_base_candidate_id: null,
        expected_input_sha256: preview.input_sha256,
        expected_preview_sha256: "f".repeat(64),
        reason: "Synthetic review",
        source_evidence_reviewed: true,
        account_allocation_reviewed: true,
        settled_balance_basis_reviewed: true,
        full_replacement_reviewed: true,
        acknowledged_changed_activity_ids: [],
        acknowledged_removed_activity_ids: [],
      },
    },
    packet: ledgerPacket() as LedgerCandidate["packet"],
    preview,
    changes: {
      added_activity_ids: [],
      changed_activity_ids: [],
      removed_activity_ids: [],
      opening_changed: false,
    },
    replayed: false,
  };
}
export function ledgerPublicationPlan(): LedgerPublicationPlan {
  const row = acceptedLedgerCandidate();
  const plan_sha256 = "1".repeat(64);
  return {
    contract_version: "portfolio-ledger-publication-v1",
    status: "READY",
    portfolio_id: row.portfolio_id,
    candidate_id: row.id,
    review_id: row.review!.id,
    review_revision_number: 1,
    anchor_snapshot_id: row.anchor_snapshot_id,
    anchor_sha256: row.packet.anchor_sha256,
    candidate_input_sha256: row.input_sha256,
    candidate_preview_sha256: row.preview_sha256,
    previous_publication_id: null,
    publication_id: null,
    ownership_scope: "WHOLE_PORTFOLIO",
    cutover_at: row.as_of,
    effective_at: row.as_of,
    current_snapshot: structuredClone(ledgerAnchor.snapshot),
    current_snapshot_sha256: "2".repeat(64),
    account_ids: row.packet.accounts.map((a) => a.account_id),
    positions: row.preview.positions,
    cash: row.preview.cash,
    plan_sha256,
    confirmation_phrase: `PUBLISH LEDGER ${row.portfolio_id}/${row.id}/${plan_sha256}`,
  };
}
export function ledgerPublicationReceipt(): LedgerPublication {
  const plan = ledgerPublicationPlan();
  const id = "77777777-7777-4777-8777-777777777777";
  const reason = "Reviewed synthetic publication";
  return {
    id,
    portfolio_id: plan.portfolio_id,
    candidate_id: plan.candidate_id,
    sequence: 1,
    previous_publication_id: null,
    published_at: "2026-01-03T00:00:00Z",
    published_by: "LOCAL_USER",
    plan,
    command: {
      expected_plan_sha256: plan.plan_sha256,
      expected_previous_publication_id: null,
      confirmation: plan.confirmation_phrase,
      reason,
      ownership_transfer_reviewed: true,
      whole_portfolio_scope_reviewed: true,
      current_state_recovery_verified: true,
      holdings_confirmation: true,
    },
    snapshot: {
      id: "66666666-6666-4666-8666-666666666666",
      portfolio_id: plan.portfolio_id,
      completeness: "COMPLETE",
      actor: "LOCAL_USER",
      reason,
      source: `portfolio-ledger-publication-v1:${id}`,
      effective_at: plan.effective_at,
      recorded_at: "2026-01-03T00:00:00Z",
      positions: structuredClone(plan.positions),
      cash_positions: structuredClone(plan.cash),
    },
    snapshot_sha256: "3".repeat(64),
    replayed: false,
  };
}
