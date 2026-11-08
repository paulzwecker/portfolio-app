import { isRecord, type PortfolioLedgerAnchor } from "@/lib/domain-contracts";
import {
  inspectLedgerFile,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";
import { restoreOpeningReview } from "./ledger-opening-draft";

export type SettledActivityDraft = {
  id: string;
  accountId: string;
  kind:
    | ""
    | "DEPOSIT"
    | "WITHDRAWAL"
    | "FEE"
    | "TAX"
    | "BUY"
    | "SELL"
    | "DIVIDEND"
    | "CASH_TRANSFER";
  sequence: string;
  effectiveAt: string;
  currency: string;
  amount: string;
  sourceSha256: string;
  sourceRecordId: string;
  listingId?: string;
  quantity?: string;
  grossCash?: string;
  fees?: string;
  taxes?: string;
  tradeDate?: string;
  settlementDate?: string;
  destinationAccountId?: string;
  destinationCurrency?: string;
  destinationAmount?: string;
  destinationEffectiveAt?: string;
  destinationSourceSha256?: string;
  destinationSourceRecordId?: string;
};

const timestamp =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/;
const amount = /^(?:0|[1-9]\d{0,17})(?:\.\d{1,10})?$/;
const uuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;

export type SettledActivitySession = {
  base: LedgerReviewFile;
  cutoff: string;
  entries: SettledActivityDraft[];
};

/** Accept only an unchanged packet that this editor can reproduce completely. */
export function restoreSettledActivityReview(
  anchor: PortfolioLedgerAnchor,
  text: string,
): SettledActivitySession {
  const invalid =
    "This review cannot be edited in the settled activity form. Use the private file workflow for its full contents.";
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
  const entries: SettledActivityDraft[] = packet.activity.map(
    (item: unknown) => {
      if (
        !isRecord(item) ||
        !isRecord(item.evidence) ||
        typeof item.id !== "string" ||
        typeof item.account_id !== "string" ||
        (item.kind !== "DEPOSIT" &&
          item.kind !== "WITHDRAWAL" &&
          item.kind !== "FEE" &&
          item.kind !== "TAX" &&
          item.kind !== "BUY" &&
          item.kind !== "SELL" &&
          item.kind !== "DIVIDEND" &&
          item.kind !== "CASH_TRANSFER") ||
        typeof item.sequence !== "number" ||
        !Number.isSafeInteger(item.sequence) ||
        typeof item.effective_at !== "string" ||
        typeof item.currency !== "string" ||
        typeof item.evidence.source_sha256 !== "string" ||
        typeof item.evidence.source_record_id !== "string"
      )
        throw new Error(invalid);
      const trade = item.kind === "BUY" || item.kind === "SELL";
      const dividend = item.kind === "DIVIDEND";
      const transfer = item.kind === "CASH_TRANSFER";
      if (
        transfer &&
        (!isRecord(item.destination) ||
          !isRecord(item.destination.evidence) ||
          [
            item.destination.account_id,
            item.destination.currency,
            item.destination.amount,
            item.destination.effective_at,
            item.destination.evidence.source_sha256,
            item.destination.evidence.source_record_id,
          ].some((value) => typeof value !== "string"))
      )
        throw new Error(invalid);
      if (
        trade
          ? [
              item.listing_id,
              item.quantity,
              item.gross_cash,
              item.fees,
              item.taxes,
              item.trade_date,
              item.settlement_date,
            ].some((value) => typeof value !== "string")
          : dividend
            ? [item.listing_id, item.gross_cash, item.fees, item.taxes].some(
                (value) => typeof value !== "string",
              )
            : typeof item.amount !== "string"
      )
        throw new Error(invalid);
      return {
        id: item.id,
        accountId: item.account_id,
        kind: item.kind,
        sequence: String(item.sequence),
        effectiveAt: item.effective_at,
        currency: item.currency,
        amount: trade || dividend ? "" : (item.amount as string),
        ...(trade
          ? {
              listingId: item.listing_id as string,
              quantity: item.quantity as string,
              grossCash: item.gross_cash as string,
              fees: item.fees as string,
              taxes: item.taxes as string,
              tradeDate: item.trade_date as string,
              settlementDate: item.settlement_date as string,
            }
          : dividend
            ? {
                listingId: item.listing_id as string,
                grossCash: item.gross_cash as string,
                fees: item.fees as string,
                taxes: item.taxes as string,
              }
            : {}),
        sourceSha256: item.evidence.source_sha256,
        sourceRecordId: item.evidence.source_record_id,
        ...(transfer &&
        isRecord(item.destination) &&
        isRecord(item.destination.evidence)
          ? {
              destinationAccountId: item.destination.account_id as string,
              destinationCurrency: item.destination.currency as string,
              destinationAmount: item.destination.amount as string,
              destinationEffectiveAt: item.destination.effective_at as string,
              destinationSourceSha256: item.destination.evidence
                .source_sha256 as string,
              destinationSourceRecordId: item.destination.evidence
                .source_record_id as string,
            }
          : {}),
      };
    },
  );
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
      buildSettledActivityReview(anchor, base, packet.as_of, entries).text !==
      text
    )
      throw new Error(invalid);
    return { base, cutoff: packet.as_of, entries };
  } catch {
    throw new Error(invalid);
  }
}

export function buildSettledActivityReview(
  anchor: PortfolioLedgerAnchor,
  base: LedgerReviewFile,
  cutoff: string,
  entries: SettledActivityDraft[],
): LedgerReviewFile {
  const accounts = restoreOpeningReview(anchor, base.text);
  if (!timestamp.test(cutoff) || !Number.isFinite(Date.parse(cutoff)))
    throw new Error(
      "Enter a cutoff timestamp with seconds and an explicit UTC offset.",
    );
  if (entries.length < 1 || entries.length > 1000)
    throw new Error("Add between one and 1,000 activity records.");
  const brokerIds = new Set(
    accounts.filter((a) => a.kind === "BROKERAGE").map((a) => a.id),
  );
  const sources = new Set(
    accounts.map((a) => `${a.sourceSha256}:${a.sourceRecordId.trim()}`),
  );
  const ids = new Set<string>();
  const sequences = new Set<string>();
  const activity = entries.map((entry, index) => {
    const label = `Activity record ${index + 1}`;
    if (!uuid.test(entry.id) || ids.has(entry.id.toLowerCase()))
      throw new Error(`${label} needs a distinct identity.`);
    ids.add(entry.id.toLowerCase());
    if (!brokerIds.has(entry.accountId))
      throw new Error(`${label} needs an evidenced brokerage account.`);
    if (
      ![
        "DEPOSIT",
        "WITHDRAWAL",
        "FEE",
        "TAX",
        "BUY",
        "SELL",
        "DIVIDEND",
        "CASH_TRANSFER",
      ].includes(entry.kind)
    )
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
    if (!/^[A-Z]{3}$/.test(entry.currency))
      throw new Error(`${label} needs a currency.`);
    const trade = entry.kind === "BUY" || entry.kind === "SELL";
    const dividend = entry.kind === "DIVIDEND";
    const transfer = entry.kind === "CASH_TRANSFER";
    if (
      !transfer &&
      [
        entry.destinationAccountId,
        entry.destinationCurrency,
        entry.destinationAmount,
        entry.destinationEffectiveAt,
        entry.destinationSourceSha256,
        entry.destinationSourceRecordId,
      ].some(Boolean)
    )
      throw new Error(`${label} contains unexpected destination details.`);
    if (trade || dividend) {
      const listing = anchor.listings.find(
        (item) => item.listing_id === entry.listingId,
      );
      if (!listing || (trade && listing.currency !== entry.currency))
        throw new Error(
          `${label} needs an anchored listing${trade ? " and its exact trading currency" : ""}.`,
        );
      if (
        entry.amount ||
        (trade &&
          (!entry.quantity ||
            !amount.test(entry.quantity) ||
            !/[1-9]/.test(entry.quantity))) ||
        (dividend &&
          [entry.quantity, entry.tradeDate, entry.settlementDate].some(
            Boolean,
          )) ||
        !entry.grossCash ||
        !amount.test(entry.grossCash) ||
        !/[1-9]/.test(entry.grossCash) ||
        entry.fees === undefined ||
        !amount.test(entry.fees) ||
        entry.taxes === undefined ||
        !amount.test(entry.taxes)
      )
        throw new Error(
          `${label} needs ${trade ? "positive exact quantity and " : ""}positive gross cash, and explicit nonnegative fees and taxes.`,
        );
      if (
        trade &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(entry.tradeDate ?? "") ||
          !/^\d{4}-\d{2}-\d{2}$/.test(entry.settlementDate ?? ""))
      )
        throw new Error(`${label} needs explicit trade and settlement dates.`);
    } else if (
      !amount.test(entry.amount) ||
      !/[1-9]/.test(entry.amount) ||
      [
        entry.listingId,
        entry.quantity,
        entry.grossCash,
        entry.fees,
        entry.taxes,
        entry.tradeDate,
        entry.settlementDate,
      ].some(Boolean)
    )
      throw new Error(
        `${label} needs a positive exact decimal amount and no trade fields.`,
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
    if (transfer) {
      if (
        !entry.destinationAccountId ||
        !brokerIds.has(entry.destinationAccountId) ||
        entry.destinationAccountId === entry.accountId
      )
        throw new Error(
          `${label} needs a different evidenced destination account.`,
        );
      if (
        !entry.destinationCurrency ||
        !/^[A-Z]{3}$/.test(entry.destinationCurrency) ||
        !entry.destinationAmount ||
        !amount.test(entry.destinationAmount) ||
        !/[1-9]/.test(entry.destinationAmount) ||
        !entry.destinationEffectiveAt ||
        !timestamp.test(entry.destinationEffectiveAt) ||
        !Number.isFinite(Date.parse(entry.destinationEffectiveAt))
      )
        throw new Error(
          `${label} needs the destination currency, positive exact amount and booking timestamp.`,
        );
      if (
        !entry.destinationSourceSha256 ||
        !/^[a-f0-9]{64}$/.test(entry.destinationSourceSha256) ||
        !entry.destinationSourceRecordId?.trim() ||
        entry.destinationSourceRecordId.trim().length > 200
      )
        throw new Error(`${label} needs destination source evidence.`);
      const destinationSource = `${entry.destinationSourceSha256}:${entry.destinationSourceRecordId.trim()}`;
      if (sources.has(destinationSource))
        throw new Error(`${label} duplicates another source record.`);
      sources.add(destinationSource);
    }
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
      ...(trade
        ? {
            listing_id: entry.listingId,
            quantity: entry.quantity,
            gross_cash: entry.grossCash,
            fees: entry.fees,
            taxes: entry.taxes,
            trade_date: entry.tradeDate,
            settlement_date: entry.settlementDate,
          }
        : dividend
          ? {
              listing_id: entry.listingId,
              gross_cash: entry.grossCash,
              fees: entry.fees,
              taxes: entry.taxes,
            }
          : transfer
            ? {
                amount: entry.amount,
                destination: {
                  account_id: entry.destinationAccountId,
                  currency: entry.destinationCurrency,
                  amount: entry.destinationAmount,
                  effective_at: entry.destinationEffectiveAt,
                  evidence: {
                    source_sha256: entry.destinationSourceSha256,
                    source_record_id: entry.destinationSourceRecordId,
                  },
                },
              }
            : { amount: entry.amount }),
    };
  });
  const packet = JSON.parse(base.text);
  packet.as_of = cutoff;
  packet.activity = activity;
  return inspectLedgerFile(JSON.stringify(packet), "settled-activity.json");
}
