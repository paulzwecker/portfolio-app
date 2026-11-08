import type { components } from "@portfolio/contracts";
import {
  isRecord,
  isSnapshotRead,
  type LedgerCandidate,
} from "@/lib/domain-contracts";

export type LedgerPublicationPlan =
  components["schemas"]["LedgerPublicationPreviewRead"];
export type LedgerPublication = components["schemas"]["LedgerPublicationRead"];
export type LedgerPublicationCommand =
  components["schemas"]["LedgerPublicationCreate"];
export type LedgerOwnership = components["schemas"]["LedgerOwnershipRead"];

const uuid = (v: unknown): v is string =>
  typeof v === "string" &&
  /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(v);
const nullableUuid = (v: unknown) => v === null || uuid(v);
const digest = (v: unknown) =>
  typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const timestamp = (v: unknown): v is string =>
  typeof v === "string" &&
  /(?:Z|[+-]\d{2}:\d{2})$/.test(v) &&
  Number.isFinite(Date.parse(v));
const quantity = (v: unknown): v is string =>
  typeof v === "string" && /^\d+(?:\.\d+)?$/.test(v);
const currency = (v: unknown): v is string =>
  typeof v === "string" && /^[A-Z]{3}$/.test(v);
const positiveInteger = (v: unknown) => Number.isInteger(v) && Number(v) >= 1;
const text = (v: unknown): v is string =>
  typeof v === "string" && v.trim().length > 0;
const uniqueRows = (rows: Record<string, unknown>[], key: string) =>
  new Set(rows.map((row) => row[key])).size === rows.length;
function positions(
  v: unknown,
): v is { listing_id: string; quantity: string }[] {
  return (
    Array.isArray(v) &&
    v.every(
      (row) => isRecord(row) && uuid(row.listing_id) && quantity(row.quantity),
    ) &&
    uniqueRows(v, "listing_id")
  );
}
function cash(v: unknown): v is { currency: string; balance: string }[] {
  return (
    Array.isArray(v) &&
    v.every(
      (row) => isRecord(row) && currency(row.currency) && quantity(row.balance),
    ) &&
    uniqueRows(v, "currency")
  );
}
// Compare exact decimal text without passing financial values through Number.
function decimalText(v: string) {
  const [whole, fraction = ""] = v.split(".");
  const tail = fraction.replace(/0+$/, "");
  return whole.replace(/^0+(?=\d)/, "") + (tail ? `.${tail}` : "");
}
function sameBalances(
  a: { listing_id: string; quantity: string }[],
  b: { listing_id: string; quantity: string }[],
  x: { currency: string; balance: string }[],
  y: { currency: string; balance: string }[],
) {
  return (
    a.length === b.length &&
    a.every((row) =>
      b.some(
        (other) =>
          row.listing_id === other.listing_id &&
          decimalText(row.quantity) === decimalText(other.quantity),
      ),
    ) &&
    x.length === y.length &&
    x.every((row) =>
      y.some(
        (other) =>
          row.currency === other.currency &&
          decimalText(row.balance) === decimalText(other.balance),
      ),
    )
  );
}
export function isLedgerPublicationPlan(
  value: unknown,
): value is LedgerPublicationPlan {
  if (
    !isRecord(value) ||
    value.contract_version !== "portfolio-ledger-publication-v1" ||
    !["READY", "ALREADY_PUBLISHED"].includes(value.status as string) ||
    ![
      value.portfolio_id,
      value.candidate_id,
      value.review_id,
      value.anchor_snapshot_id,
    ].every(uuid) ||
    !positiveInteger(value.review_revision_number) ||
    !nullableUuid(value.previous_publication_id) ||
    !nullableUuid(value.publication_id) ||
    value.ownership_scope !== "WHOLE_PORTFOLIO" ||
    ![
      value.anchor_sha256,
      value.candidate_input_sha256,
      value.candidate_preview_sha256,
      value.current_snapshot_sha256,
      value.plan_sha256,
    ].every(digest) ||
    !timestamp(value.cutover_at) ||
    !timestamp(value.effective_at) ||
    !isSnapshotRead(value.current_snapshot) ||
    !Array.isArray(value.account_ids) ||
    value.account_ids.length < 1 ||
    value.account_ids.length > 20 ||
    !value.account_ids.every(uuid) ||
    new Set(value.account_ids).size !== value.account_ids.length ||
    !positions(value.positions) ||
    !cash(value.cash)
  )
    return false;
  const snapshot = value.current_snapshot;
  if (
    snapshot.portfolio_id !== value.portfolio_id ||
    snapshot.completeness !== "COMPLETE" ||
    !positions(snapshot.positions) ||
    !cash(snapshot.cash_positions) ||
    !timestamp(snapshot.effective_at) ||
    !timestamp(snapshot.recorded_at) ||
    Date.parse(snapshot.effective_at) >= Date.parse(value.effective_at) ||
    Date.parse(value.cutover_at) > Date.parse(value.effective_at)
  )
    return false;
  if (
    value.previous_publication_id === null
      ? snapshot.id !== value.anchor_snapshot_id ||
        snapshot.source?.startsWith("portfolio-ledger-publication-v1:")
      : snapshot.source !==
          `portfolio-ledger-publication-v1:${value.previous_publication_id}` ||
        snapshot.actor !== "LOCAL_USER"
  )
    return false;
  return (
    (value.status === "READY") === (value.publication_id === null) &&
    value.confirmation_phrase ===
      `PUBLISH LEDGER ${value.portfolio_id}/${value.candidate_id}/${value.plan_sha256}`
  );
}
export function publicationMatchesCandidate(
  plan: LedgerPublicationPlan,
  candidate: LedgerCandidate,
) {
  return (
    candidate.status === "ACCEPTED" &&
    candidate.review?.decision === "ACCEPT" &&
    plan.portfolio_id === candidate.portfolio_id &&
    plan.candidate_id === candidate.id &&
    plan.review_id === candidate.review.id &&
    plan.review_revision_number === candidate.review.revision_number &&
    plan.anchor_snapshot_id === candidate.anchor_snapshot_id &&
    plan.anchor_sha256 === candidate.packet.anchor_sha256 &&
    plan.candidate_input_sha256 === candidate.input_sha256 &&
    plan.candidate_preview_sha256 === candidate.preview_sha256 &&
    Date.parse(plan.effective_at) === Date.parse(candidate.as_of) &&
    plan.account_ids.length === candidate.packet.accounts.length &&
    candidate.packet.accounts.every((account) =>
      plan.account_ids.includes(account.account_id),
    ) &&
    sameBalances(
      plan.positions,
      candidate.preview.positions,
      plan.cash,
      candidate.preview.cash,
    )
  );
}
export function isLedgerPublication(
  value: unknown,
): value is LedgerPublication {
  if (
    !isRecord(value) ||
    ![value.id, value.portfolio_id, value.candidate_id].every(uuid) ||
    !positiveInteger(value.sequence) ||
    !nullableUuid(value.previous_publication_id) ||
    !timestamp(value.published_at) ||
    value.published_by !== "LOCAL_USER" ||
    typeof value.replayed !== "boolean" ||
    !digest(value.snapshot_sha256) ||
    !isLedgerPublicationPlan(value.plan) ||
    !isRecord(value.command) ||
    !isSnapshotRead(value.snapshot)
  )
    return false;
  const { plan, snapshot, command } = value;
  if (
    plan.status !== "READY" ||
    plan.portfolio_id !== value.portfolio_id ||
    plan.candidate_id !== value.candidate_id ||
    plan.previous_publication_id !== value.previous_publication_id ||
    (value.sequence === 1) !== (value.previous_publication_id === null) ||
    snapshot.portfolio_id !== value.portfolio_id ||
    snapshot.completeness !== "COMPLETE" ||
    snapshot.actor !== "LOCAL_USER" ||
    snapshot.source !== `portfolio-ledger-publication-v1:${value.id}` ||
    !timestamp(snapshot.effective_at) ||
    !timestamp(snapshot.recorded_at) ||
    Date.parse(snapshot.effective_at) !== Date.parse(plan.effective_at) ||
    Date.parse(snapshot.recorded_at) !== Date.parse(value.published_at) ||
    !positions(snapshot.positions) ||
    !cash(snapshot.cash_positions) ||
    !sameBalances(
      plan.positions,
      snapshot.positions,
      plan.cash,
      snapshot.cash_positions,
    )
  )
    return false;
  return (
    command.expected_plan_sha256 === plan.plan_sha256 &&
    command.expected_previous_publication_id === plan.previous_publication_id &&
    command.confirmation === plan.confirmation_phrase &&
    text(command.reason) &&
    command.reason.length <= 1000 &&
    snapshot.reason === command.reason &&
    command.ownership_transfer_reviewed === true &&
    command.whole_portfolio_scope_reviewed === true &&
    command.current_state_recovery_verified === true &&
    command.holdings_confirmation === true
  );
}
export function isLedgerOwnership(value: unknown): value is LedgerOwnership {
  return (
    isRecord(value) &&
    uuid(value.portfolio_id) &&
    value.scope === "WHOLE_PORTFOLIO" &&
    (value.source === "OBSERVED_SNAPSHOT"
      ? value.latest_publication === null
      : value.source === "ACCEPTED_LEDGER" &&
        isLedgerPublication(value.latest_publication) &&
        value.latest_publication.portfolio_id === value.portfolio_id)
  );
}
