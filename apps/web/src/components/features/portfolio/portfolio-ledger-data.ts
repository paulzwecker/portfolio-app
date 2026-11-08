import { type LedgerCandidate, isRecord } from "@/lib/domain-contracts";

export const ledgerFileLimit = 1_000_000;

export type LedgerReviewFile = {
  text: string;
  name: string;
  anchorSnapshotId: string;
  anchorSha256: string;
  asOf: string;
  accountNames: Record<string, string>;
  evidence: {
    role: string;
    accountId: string;
    reference: string;
    sha256: string;
  }[];
};

/** Inspect identity/labels only. The original bytes supply all financial inputs. */
export function inspectLedgerFile(
  text: string,
  name: string,
): LedgerReviewFile {
  if (new TextEncoder().encode(text).byteLength > ledgerFileLimit)
    throw new Error("Choose a ledger review JSON file smaller than 1 MB.");
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("Choose a valid ledger review JSON file.");
  }
  return ledgerFileMetadata(value, text, name);
}

export function savedLedgerFile(
  packet: LedgerCandidate["packet"],
): LedgerReviewFile {
  return ledgerFileMetadata(
    packet,
    JSON.stringify(packet),
    "saved-ledger-packet.json",
  );
}

function ledgerFileMetadata(
  value: unknown,
  text: string,
  name: string,
): LedgerReviewFile {
  if (
    !isRecord(value) ||
    !["portfolio-ledger-preview-v1", "portfolio-ledger-preview-v2"].includes(
      value.contract_version as string,
    ) ||
    typeof value.anchor_snapshot_id !== "string" ||
    !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(
      value.anchor_snapshot_id,
    ) ||
    typeof value.anchor_sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.anchor_sha256) ||
    typeof value.as_of !== "string" ||
    !Number.isFinite(Date.parse(value.as_of)) ||
    !Array.isArray(value.accounts) ||
    value.accounts.length > 20
  )
    throw new Error(
      "The file needs a supported portfolio-ledger-preview-v1 or v2 contract and an exact anchor ID/hash.",
    );
  const accountNames: Record<string, string> = {};
  for (const account of value.accounts) {
    if (
      isRecord(account) &&
      typeof account.account_id === "string" &&
      typeof account.name === "string" &&
      account.name.length <= 200
    )
      accountNames[account.account_id.toLowerCase()] = account.name;
  }
  const evidence: LedgerReviewFile["evidence"] = [];
  const activity = Array.isArray(value.activity) ? value.activity : [];
  const ending =
    isRecord(value.ending_statement) &&
    Array.isArray(value.ending_statement.accounts)
      ? value.ending_statement.accounts
      : [];
  for (const [role, records] of [
    ["Opening", value.accounts],
    ["Ending", ending],
    ["Activity", activity],
    [
      "Transfer receipt",
      activity
        .filter(
          (record) =>
            isRecord(record) &&
            ["CASH_TRANSFER", "SECURITY_TRANSFER"].includes(
              record.kind as string,
            ),
        )
        .map((record) => record.destination),
    ],
  ] as const) {
    for (const record of records) {
      if (
        isRecord(record) &&
        isRecord(record.evidence) &&
        typeof record.account_id === "string" &&
        typeof record.evidence.source_record_id === "string" &&
        record.evidence.source_record_id.length <= 200 &&
        typeof record.evidence.source_sha256 === "string" &&
        /^[a-f0-9]{64}$/.test(record.evidence.source_sha256)
      )
        evidence.push({
          role,
          accountId: record.account_id.toLowerCase(),
          reference: record.evidence.source_record_id,
          sha256: record.evidence.source_sha256,
        });
    }
  }
  return {
    text,
    name,
    accountNames,
    anchorSnapshotId: value.anchor_snapshot_id.toLowerCase(),
    anchorSha256: value.anchor_sha256,
    asOf: value.as_of,
    evidence,
  };
}

export function downloadLedgerJson(value: unknown, filename: string) {
  downloadLedgerText(JSON.stringify(value, null, 2), filename);
}

export function downloadLedgerText(text: string, filename: string) {
  const url = URL.createObjectURL(
    new Blob([text], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Preserve original financial text when adding submission metadata. */
export function ledgerStageBody(
  file: LedgerReviewFile,
  submissionId: string,
  base: string | null,
  inputSha256: string,
  reason: string,
) {
  const header = JSON.stringify({
    submission_id: submissionId,
    expected_base_candidate_id: base,
    expected_input_sha256: inputSha256,
    reason,
  });
  return `${header.slice(0, -1)},"proposal":${file.text}}`;
}
