import type { components } from "@portfolio/contracts";

export type EarningsInbox = components["schemas"]["Inbox"];
type Row = EarningsInbox["rows"][number];
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const optional = (v: unknown) => v === null || typeof v === "string";
const numeric = (v: unknown) =>
  v === null ||
  (typeof v === "string" && /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(v));
const count = (v: unknown) =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
function row(v: unknown): v is Row {
  return (
    record(v) &&
    ["listing_id", "listing", "company", "title", "outcome"].every(
      (k) => typeof v[k] === "string",
    ) &&
    (v.url === null ||
      (typeof v.url === "string" && /^https:\/\//i.test(v.url))) &&
    [
      "period",
      "published_at",
      "rationale",
      "passage",
      "comparison",
      "proposal_id",
      "decision_note",
      "reviewed_at",
      "price_status",
    ].every((k) => optional(v[k])) &&
    ["irr_before", "irr_after", "impact_bps"].every((k) => numeric(v[k])) &&
    optional(v.company_id) &&
    typeof v.crosses_hurdle === "boolean" &&
    (v.revision_number === null || count(v.revision_number))
  );
}
export function isEarningsInbox(v: unknown): v is EarningsInbox {
  return (
    record(v) &&
    typeof v.portfolio_id === "string" &&
    optional(v.snapshot_id) &&
    optional(v.effective_at) &&
    count(v.listing_count) &&
    count(v.modeled_count) &&
    Array.isArray(v.rows) &&
    v.rows.every(row)
  );
}
