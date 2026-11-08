import { isRecord, type PortfolioLedgerAnchor } from "@/lib/domain-contracts";
import {
  inspectLedgerFile,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";
import { restoreOpeningReview } from "./ledger-opening-draft";

export type CashActivityDraft = {
  id: string;
  accountId: string;
  kind: "" | "DEPOSIT" | "WITHDRAWAL" | "FEE" | "TAX";
  sequence: string;
  effectiveAt: string;
  currency: string;
  amount: string;
  sourceSha256: string;
  sourceRecordId: string;
};

const timestamp =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;
const amount = /^(?:0|[1-9]\d{0,17})(?:\.\d{1,10})?$/;
const uuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;

export type CashActivitySession = {
  base: LedgerReviewFile;
  cutoff: string;
  entries: CashActivityDraft[];
};

/** Accept only an unchanged packet that this cash editor can reproduce completely. */
export function restoreCashActivityReview(
  anchor: PortfolioLedgerAnchor,
  text: string,
): CashActivitySession {
  const invalid =
    "This review cannot be edited in the cash form. Use the private file workflow for its full contents.";
  let packet: unknown;
  try {
    packet = JSON.parse(text);
  } catch {
    throw new Error(invalid);
  }
  if (
    !isRecord(packet) ||
    typeof packet.as_of !== "string" ||
    !Array.isArray(packet.activity) ||
    packet.activity.length < 1 ||
    packet.activity.length > 1000 ||
    packet.ending_statement !== null
  )
    throw new Error(invalid);
  const entries: CashActivityDraft[] = packet.activity.map((item: unknown) => {
    if (
      !isRecord(item) ||
      !isRecord(item.evidence) ||
      typeof item.id !== "string" ||
      typeof item.account_id !== "string" ||
      (item.kind !== "DEPOSIT" &&
        item.kind !== "WITHDRAWAL" &&
        item.kind !== "FEE" &&
        item.kind !== "TAX") ||
      typeof item.sequence !== "number" ||
      !Number.isSafeInteger(item.sequence) ||
      typeof item.effective_at !== "string" ||
      typeof item.currency !== "string" ||
      typeof item.amount !== "string" ||
      typeof item.evidence.source_sha256 !== "string" ||
      typeof item.evidence.source_record_id !== "string"
    )
      throw new Error(invalid);
    return {
      id: item.id,
      accountId: item.account_id,
      kind: item.kind,
      sequence: String(item.sequence),
      effectiveAt: item.effective_at,
      currency: item.currency,
      amount: item.amount,
      sourceSha256: item.evidence.source_sha256,
      sourceRecordId: item.evidence.source_record_id,
    };
  });
  try {
    const base = inspectLedgerFile(
      JSON.stringify({
        ...packet,
        as_of: anchor.snapshot.effective_at,
        activity: [],
        ending_statement: null,
      }),
      "opening-balances.json",
    );
    if (
      buildCashActivityReview(anchor, base, packet.as_of, entries).text !== text
    )
      throw new Error(invalid);
    return { base, cutoff: packet.as_of, entries };
  } catch {
    throw new Error(invalid);
  }
}

export function buildCashActivityReview(
  anchor: PortfolioLedgerAnchor,
  base: LedgerReviewFile,
  cutoff: string,
  entries: CashActivityDraft[],
): LedgerReviewFile {
  const accounts = restoreOpeningReview(anchor, base.text);
  if (!timestamp.test(cutoff) || !Number.isFinite(Date.parse(cutoff)))
    throw new Error(
      "Enter a cutoff timestamp with seconds and an explicit UTC offset.",
    );
  if (entries.length < 1 || entries.length > 1000)
    throw new Error("Add between one and 1,000 cash records.");
  const brokerIds = new Set(
    accounts.filter((a) => a.kind === "BROKERAGE").map((a) => a.id),
  );
  const sources = new Set(
    accounts.map((a) => `${a.sourceSha256}:${a.sourceRecordId.trim()}`),
  );
  const ids = new Set<string>();
  const sequences = new Set<string>();
  const activity = entries.map((entry, index) => {
    const label = `Cash record ${index + 1}`;
    if (!uuid.test(entry.id) || ids.has(entry.id.toLowerCase()))
      throw new Error(`${label} needs a distinct identity.`);
    ids.add(entry.id.toLowerCase());
    if (!brokerIds.has(entry.accountId))
      throw new Error(`${label} needs an evidenced brokerage account.`);
    if (!["DEPOSIT", "WITHDRAWAL", "FEE", "TAX"].includes(entry.kind))
      throw new Error(`${label} needs a supported type.`);
    if (
      !/^(?:[1-9]\d{0,2}|1000)$/.test(entry.sequence) ||
      sequences.has(entry.sequence)
    )
      throw new Error(`${label} needs a unique sequence from 1 to 1,000.`);
    sequences.add(entry.sequence);
    if (
      !timestamp.test(entry.effectiveAt) ||
      !Number.isFinite(Date.parse(entry.effectiveAt))
    )
      throw new Error(
        `${label} needs a booking timestamp with seconds and an explicit UTC offset.`,
      );
    if (
      !/^[A-Z]{3}$/.test(entry.currency) ||
      !amount.test(entry.amount) ||
      !/[1-9]/.test(entry.amount)
    )
      throw new Error(
        `${label} needs a currency and positive exact decimal amount.`,
      );
    if (
      !/^[a-f0-9]{64}$/.test(entry.sourceSha256) ||
      !entry.sourceRecordId.trim() ||
      entry.sourceRecordId.trim().length > 200
    )
      throw new Error(`${label} needs a source hash and record reference.`);
    const source = `${entry.sourceSha256}:${entry.sourceRecordId.trim()}`;
    if (sources.has(source))
      throw new Error(`${label} duplicates another source record.`);
    sources.add(source);
    return {
      id: entry.id,
      account_id: entry.accountId,
      kind: entry.kind,
      sequence: Number(entry.sequence),
      effective_at: entry.effectiveAt,
      evidence: {
        source_sha256: entry.sourceSha256,
        source_record_id: entry.sourceRecordId,
      },
      currency: entry.currency,
      amount: entry.amount,
    };
  });
  const packet = JSON.parse(base.text);
  packet.as_of = cutoff;
  packet.activity = activity;
  return inspectLedgerFile(JSON.stringify(packet), "cash-activity.json");
}
