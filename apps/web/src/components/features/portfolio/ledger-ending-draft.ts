import { isRecord, type PortfolioLedgerAnchor } from "@/lib/domain-contracts";
import {
  inspectLedgerFile,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";
import {
  restoreOpeningReview,
  type OpeningAccountDraft,
} from "./ledger-opening-draft";
import { restoreSettledActivityReview } from "./ledger-settled-activity";
import { ledgerAvailableListings, type LedgerListing } from "./ledger-listings";

export type EndingAccountDraft = {
  accountId: string;
  sourceSha256: string;
  sourceRecordId: string;
  positions: { id: string; listingId: string; quantity: string }[];
  cash: { id: string; currency: string; balance: string }[];
};

const amount = /^(?:0|[1-9]\d{0,17})(?:\.\d{1,10})?$/;

export type EndingSession = {
  file: LedgerReviewFile;
  opening: OpeningAccountDraft[];
  accounts: EndingAccountDraft[];
};

/** Preserve every source field by accepting only a packet reproducible by this form. */
export function restoreEndingReview(
  anchor: PortfolioLedgerAnchor,
  text: string,
  extraListings: readonly LedgerListing[] = [],
): EndingSession {
  const invalid =
    "This review cannot be edited in the ending form. Use the private file workflow for its full contents.";
  let packet: unknown;
  try {
    packet = JSON.parse(text);
  } catch {
    throw new Error(invalid);
  }
  if (
    !isRecord(packet) ||
    !isRecord(packet.ending_statement) ||
    !Array.isArray(packet.ending_statement.accounts) ||
    packet.ending_statement.accounts.length > 20
  )
    throw new Error(invalid);
  const accounts: EndingAccountDraft[] = packet.ending_statement.accounts.map(
    (value: unknown) => {
      if (
        !isRecord(value) ||
        !isRecord(value.evidence) ||
        typeof value.account_id !== "string" ||
        typeof value.evidence.source_sha256 !== "string" ||
        typeof value.evidence.source_record_id !== "string" ||
        !Array.isArray(value.positions) ||
        !Array.isArray(value.cash) ||
        value.positions.length > 1000 ||
        value.cash.length > 100
      )
        throw new Error(invalid);
      const positions = value.positions.map((row: unknown) => {
        if (
          !isRecord(row) ||
          typeof row.listing_id !== "string" ||
          typeof row.quantity !== "string"
        )
          throw new Error(invalid);
        return {
          id: crypto.randomUUID(),
          listingId: row.listing_id,
          quantity: row.quantity,
        };
      });
      const cash = value.cash.map((row: unknown) => {
        if (
          !isRecord(row) ||
          typeof row.currency !== "string" ||
          typeof row.balance !== "string"
        )
          throw new Error(invalid);
        return {
          id: crypto.randomUUID(),
          currency: row.currency,
          balance: row.balance,
        };
      });
      return {
        accountId: value.account_id,
        sourceSha256: value.evidence.source_sha256,
        sourceRecordId: value.evidence.source_record_id,
        positions,
        cash,
      };
    },
  );
  try {
    const file = inspectLedgerFile(
      JSON.stringify({ ...packet, ending_statement: null }),
      "review-before-ending.json",
    );
    const opening = endingOpeningAccounts(anchor, file, extraListings);
    if (
      buildEndingReview(anchor, file, accounts, true, extraListings).text !==
      text
    )
      throw new Error(invalid);
    return { file, opening, accounts };
  } catch {
    throw new Error(invalid);
  }
}

/** Only guided packets that can be reproduced in full can be extended here. */
export function endingOpeningAccounts(
  anchor: PortfolioLedgerAnchor,
  base: LedgerReviewFile,
  extraListings: readonly LedgerListing[] = [],
): OpeningAccountDraft[] {
  let packet: unknown;
  try {
    packet = JSON.parse(base.text);
  } catch {
    throw new Error(
      "Use a supported, validated guided review as the ending source.",
    );
  }
  if (
    !isRecord(packet) ||
    !Array.isArray(packet.activity) ||
    packet.ending_statement !== null
  )
    throw new Error(
      "Use a supported, validated guided review without an ending statement.",
    );
  if (packet.activity.length === 0)
    return restoreOpeningReview(anchor, base.text);
  return restoreOpeningReview(
    anchor,
    restoreSettledActivityReview(anchor, base.text, extraListings).base.text,
  );
}

export function buildEndingReview(
  anchor: PortfolioLedgerAnchor,
  base: LedgerReviewFile,
  accounts: EndingAccountDraft[],
  confirmed: boolean,
  extraListings: readonly LedgerListing[] = [],
): LedgerReviewFile {
  const opening = endingOpeningAccounts(anchor, base, extraListings);
  if (!confirmed)
    throw new Error(
      "Confirm that every ending observation uses the review cutoff.",
    );
  if (
    accounts.length !== opening.length ||
    new Set(accounts.map((a) => a.accountId)).size !== opening.length ||
    opening.some((a) => !accounts.some((item) => item.accountId === a.id))
  )
    throw new Error(
      "Provide exactly one ending observation for each opening account.",
    );
  if (
    accounts.reduce((count, a) => count + a.positions.length, 0) > 1000 ||
    accounts.reduce((count, a) => count + a.cash.length, 0) > 100
  )
    throw new Error(
      "The ending contract supports 1,000 position rows and 100 cash rows.",
    );
  const listings = new Set(
    ledgerAvailableListings(anchor, extraListings).map(
      (item) => item.listing_id,
    ),
  );
  const sources = new Set<string>();
  const endingAccounts = accounts.map((account, index) => {
    const label = `Ending account ${index + 1}`;
    if (
      !/^[a-f0-9]{64}$/.test(account.sourceSha256) ||
      !account.sourceRecordId.trim() ||
      account.sourceRecordId.trim().length > 200
    )
      throw new Error(`${label} needs a source hash and record reference.`);
    const source = `${account.sourceSha256}:${account.sourceRecordId.trim()}`;
    if (sources.has(source))
      throw new Error(`${label} duplicates another ending source record.`);
    sources.add(source);
    if (
      new Set(account.positions.map((row) => row.listingId)).size !==
        account.positions.length ||
      new Set(account.cash.map((row) => row.currency)).size !==
        account.cash.length
    )
      throw new Error(`${label} has a duplicate listing or currency.`);
    for (const row of account.positions) {
      if (!listings.has(row.listingId) || !amount.test(row.quantity))
        throw new Error(
          `${label} needs an exact listing and nonnegative decimal quantity.`,
        );
    }
    for (const row of account.cash) {
      if (!/^[A-Z]{3}$/.test(row.currency) || !amount.test(row.balance))
        throw new Error(
          `${label} needs a currency and nonnegative decimal cash balance.`,
        );
    }
    return {
      account_id: account.accountId,
      evidence: {
        source_sha256: account.sourceSha256,
        source_record_id: account.sourceRecordId,
      },
      positions: account.positions.map((row) => ({
        listing_id: row.listingId,
        quantity: row.quantity,
      })),
      cash: account.cash.map((row) => ({
        currency: row.currency,
        balance: row.balance,
      })),
    };
  });
  const packet = JSON.parse(base.text);
  packet.ending_statement = {
    effective_at: packet.as_of,
    accounts: endingAccounts,
  };
  return inspectLedgerFile(JSON.stringify(packet), "ending-statement.json");
}
