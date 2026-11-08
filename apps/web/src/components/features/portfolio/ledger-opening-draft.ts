import { isRecord, type PortfolioLedgerAnchor } from "@/lib/domain-contracts";
import {
  inspectLedgerFile,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";

export type OpeningAccountDraft = {
  id: string;
  name: string;
  kind: "BROKERAGE" | "UNALLOCATED_OPENING";
  brokerName: string;
  sourceSha256: string;
  sourceRecordId: string;
  hashing: boolean;
  positions: { id: string; listingId: string; quantity: string }[];
  cash: { id: string; currency: string; balance: string }[];
};

const uuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
// Input syntax only. Reconciliation and financial validation belong to the API.
const quantityText = /^(?:0|[1-9]\d{0,17})(?:\.\d{1,10})?$/;
export const statementFileLimit = 10 * 1024 * 1024;

export async function hashOpeningStatement(file: File): Promise<string> {
  if (file.size === 0 || file.size > statementFileLimit)
    throw new Error("Choose a nonempty statement up to 10 MiB.");
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

/** Restore only a complete, unchanged opening packet produced by this form. */
export function restoreOpeningReview(
  anchor: PortfolioLedgerAnchor,
  text: string,
): OpeningAccountDraft[] {
  const invalid =
    "Choose an unchanged opening review JSON downloaded from this form for the current anchor.";
  let packet: unknown;
  try {
    packet = JSON.parse(text);
  } catch {
    throw new Error(invalid);
  }
  if (
    !isRecord(packet) ||
    !Array.isArray(packet.accounts) ||
    packet.accounts.length > 20
  )
    throw new Error(invalid);
  const accounts: OpeningAccountDraft[] = packet.accounts.map(
    (value: unknown) => {
      if (
        !isRecord(value) ||
        !isRecord(value.evidence) ||
        typeof value.account_id !== "string" ||
        typeof value.name !== "string" ||
        (value.kind !== "BROKERAGE" && value.kind !== "UNALLOCATED_OPENING") ||
        !(
          typeof value.broker_name === "string" || value.broker_name === null
        ) ||
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
        id: value.account_id,
        name: value.name,
        kind: value.kind,
        brokerName: value.broker_name ?? "",
        sourceSha256: value.evidence.source_sha256,
        sourceRecordId: value.evidence.source_record_id,
        hashing: false,
        positions,
        cash,
      };
    },
  );
  try {
    if (buildOpeningReview(anchor, accounts, true).text !== text)
      throw new Error(invalid);
  } catch {
    throw new Error(invalid);
  }
  return accounts;
}

export function buildOpeningReview(
  anchor: PortfolioLedgerAnchor,
  accounts: OpeningAccountDraft[],
  sourceDateConfirmed: boolean,
): LedgerReviewFile {
  if (!sourceDateConfirmed)
    throw new Error(
      "Confirm that the opening source balances use the observed anchor date.",
    );
  if (accounts.length === 0 || accounts.length > 20)
    throw new Error("Declare between one and 20 evidenced opening accounts.");
  if (new Set(accounts.map((account) => account.id)).size !== accounts.length)
    throw new Error("Each opening account requires its own identity.");
  if (
    accounts.reduce((count, account) => count + account.positions.length, 0) >
      1000 ||
    accounts.reduce((count, account) => count + account.cash.length, 0) > 100
  )
    throw new Error(
      "The opening contract supports 1,000 position rows and 100 cash rows.",
    );

  const listings = new Set(
    anchor.listings.map((listing) => listing.listing_id),
  );
  const sourceKeys = new Set<string>();
  const openingAccounts = accounts.map((account, index) => {
    const label = `Account ${index + 1}`;
    if (
      !uuid.test(account.id) ||
      !account.name.trim() ||
      account.name.length > 200
    )
      throw new Error(
        `${label} needs a valid identity and a name of up to 200 characters.`,
      );
    if (!["BROKERAGE", "UNALLOCATED_OPENING"].includes(account.kind))
      throw new Error(`${label} needs an explicit account classification.`);
    if (
      account.kind === "BROKERAGE" &&
      (!account.brokerName.trim() || account.brokerName.length > 200)
    )
      throw new Error(`${label} needs the evidenced broker name.`);
    if (account.kind === "UNALLOCATED_OPENING" && account.brokerName !== "")
      throw new Error(
        `${label} has an unallocated opening and a conflicting broker name.`,
      );
    if (account.hashing || !/^[a-f0-9]{64}$/.test(account.sourceSha256))
      throw new Error(`${label} needs the source document SHA-256.`);
    if (!account.sourceRecordId.trim() || account.sourceRecordId.length > 200)
      throw new Error(
        `${label} needs an opening statement reference of up to 200 characters.`,
      );
    const sourceKey = `${account.sourceSha256}:${account.sourceRecordId}`;
    if (sourceKeys.has(sourceKey))
      throw new Error(
        "An opening source record can describe only one account.",
      );
    sourceKeys.add(sourceKey);
    if (
      new Set(account.positions.map((row) => row.listingId)).size !==
      account.positions.length
    )
      throw new Error(`${label} contains a duplicate listing.`);
    if (
      new Set(account.cash.map((row) => row.currency)).size !==
      account.cash.length
    )
      throw new Error(`${label} contains a duplicate cash currency.`);
    for (const [rowIndex, row] of account.positions.entries()) {
      if (!listings.has(row.listingId))
        throw new Error(
          `${label} needs an exact listing from the verified anchor.`,
        );
      if (!quantityText.test(row.quantity))
        throw new Error(
          `${label}, position ${rowIndex + 1} needs exact nonnegative decimal text, with a dot and up to ten decimal places.`,
        );
    }
    for (const row of account.cash) {
      if (!/^[A-Z]{3}$/.test(row.currency) || !quantityText.test(row.balance))
        throw new Error(
          `${label} cash needs a three-letter currency and exact nonnegative decimal text.`,
        );
    }
    return {
      account_id: account.id,
      name: account.name,
      kind: account.kind,
      broker_name: account.kind === "BROKERAGE" ? account.brokerName : null,
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
  return inspectLedgerFile(
    JSON.stringify({
      contract_version: "portfolio-ledger-preview-v2",
      anchor_snapshot_id: anchor.snapshot.id,
      anchor_sha256: anchor.anchor_sha256,
      as_of: anchor.snapshot.effective_at,
      accounts: openingAccounts,
      activity: [],
      ending_statement: null,
    }),
    "opening-balances.json",
  );
}
