"use client";

import { useState } from "react";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { PageSection } from "@/components/app/page-section";
import { ResponsiveDataTable } from "@/components/app/responsive-data-table";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Button } from "@/components/ui/button";
import type { PortfolioLedgerPreview } from "@/lib/domain-contracts";
import { dateTime, quantity, statusLabel } from "@/lib/display";
import {
  downloadLedgerJson,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";

type ComparisonRow = {
  domain: "POSITION" | "CASH";
  key: string;
  observed: string | null;
  projected: string | null;
  difference: string | null;
  status: string;
};

export function PortfolioLedgerResults({
  report,
  file,
}: {
  report: PortfolioLedgerPreview;
  file: LedgerReviewFile;
}) {
  const [stage, setStage] = useState<"opening" | "ending">(
    report.ending_status === "NOT_PROVIDED" ? "opening" : "ending",
  );
  const [account, setAccount] = useState("portfolio");
  const [onlyDifferences, setOnlyDifferences] = useState(true);
  const [visibleRows, setVisibleRows] = useState(50);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const listings = new Map(
    report.consumed_listings.map((item) => [item.listing_id, item]),
  );
  const allRows: ComparisonRow[] =
    stage === "opening"
      ? report.opening_reconciliation.map((row) => ({
          ...row,
          projected: row.opening,
        }))
      : report.ending_reconciliation.filter(
          (row) => (row.account_id ?? "portfolio") === account,
        );
  const rows = onlyDifferences
    ? allRows.filter((row) => row.status !== "MATCH")
    : allRows;
  const accountLabel = (id: string | null) =>
    id ? (file.accountNames[id] ?? id) : "Portfolio total";
  const assetLabel = (row: { domain: string; key: string }) => {
    if (row.domain === "CASH") return `${row.key} cash`;
    const listing = listings.get(row.key);
    return listing
      ? `${listing.ticker} · ${listing.venue} · ${listing.currency}`
      : row.key;
  };
  const exact = (value: string | null) => (
    <span className="tabular-nums" title={value ?? "Missing source row"}>
      {value === null ? "Missing" : quantity(value)}
    </span>
  );
  const statementReady = report.status === "ENDING_RECONCILED";

  return (
    <div className="space-y-6" aria-label="Ledger review result">
      <div role="status" className="space-y-2 rounded-lg border bg-card p-4">
        <StatusIndicator
          tone={report.status === "BLOCKED" ? "warning" : "positive"}
          label={
            report.status === "BLOCKED"
              ? "Review blocked"
              : statementReady
                ? "Ending statement reconciled"
                : "Opening balances reconciled"
          }
        />
        <p className="text-sm">
          {report.status === "BLOCKED"
            ? "Resolve the disclosed source or account differences before progressing."
            : statementReady
              ? "Opening, supported activity and ending observations reconcile. Account allocation and source authenticity require review."
              : "The opening matches the current snapshot. Add an evidenced ending statement to reconcile the activity period."}
        </p>
        <p className="text-xs text-muted-foreground">
          Candidate projection · {dateTime(report.as_of)} · Activity records ·{" "}
          {report.activity_count}
        </p>
      </div>

      {report.issues.length > 0 && (
        <PageSection title="Blocking issues">
          <ul className="space-y-2 rounded-lg border p-4 text-sm">
            {report.issues.slice(0, 50).map((issue, index) => (
              <li key={`${issue.code}-${index}`} className="break-words">
                <strong>{statusLabel(issue.code)}</strong> ·{" "}
                {accountLabel(issue.account_id)}
                {issue.asset_key && (
                  <>
                    {" "}
                    · {listings.get(issue.asset_key)?.ticker ?? issue.asset_key}
                  </>
                )}
              </li>
            ))}
          </ul>
          {report.issues.length > 50 && (
            <p className="text-xs text-muted-foreground">
              Showing 50 of {report.issues.length} issues. Download the full
              report for every record.
            </p>
          )}
        </PageSection>
      )}

      <PageSection
        title="Balance reconciliation"
        description="Exact native quantities and cash. Candidate minus observed supplies each difference."
      >
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-xs font-medium">
            Comparison
            <select
              className="block h-10 rounded-md border bg-background px-3 text-sm"
              value={stage}
              onChange={(e) => {
                setStage(e.target.value as "opening" | "ending");
                setVisibleRows(50);
              }}
            >
              <option value="opening">Opening snapshot</option>
              <option value="ending">Ending statement</option>
            </select>
          </label>
          {stage === "ending" && (
            <label className="space-y-1 text-xs font-medium">
              Account scope
              <select
                className="block h-10 max-w-full rounded-md border bg-background px-3 text-sm"
                value={account}
                onChange={(e) => {
                  setAccount(e.target.value);
                  setVisibleRows(50);
                }}
              >
                <option value="portfolio">Portfolio total</option>
                {Object.entries(file.accountNames).map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={onlyDifferences}
              onChange={(e) => {
                setOnlyDifferences(e.target.checked);
                setVisibleRows(50);
              }}
            />
            Differences only
          </label>
        </div>
        {stage === "ending" &&
        ["NOT_PROVIDED", "NOT_EVALUATED"].includes(report.ending_status) ? (
          <p className="rounded-lg border border-dashed p-4 text-sm">
            {report.ending_status === "NOT_PROVIDED"
              ? "An ending statement is needed for period reconciliation."
              : "Resolve the opening mismatch before ending balances can be evaluated."}
          </p>
        ) : rows.length === 0 && onlyDifferences ? (
          <p className="rounded-lg border p-4 text-sm">
            No differences in this scope. Account-level issues remain listed
            above.
          </p>
        ) : (
          <ResponsiveDataTable
            caption="Ledger balance comparison"
            rows={rows.slice(0, visibleRows)}
            getRowKey={(row) => `${row.domain}-${row.key}`}
            columns={[
              {
                id: "asset",
                header: "Exact asset",
                className: "w-[30%]",
                render: assetLabel,
              },
              {
                id: "observed",
                header: "Observed",
                render: (row) => exact(row.observed),
              },
              {
                id: "candidate",
                header: "Candidate",
                render: (row) => exact(row.projected),
              },
              {
                id: "difference",
                header: "Difference",
                render: (row) => exact(row.difference),
              },
              {
                id: "status",
                header: "Status",
                render: (row) => (
                  <StatusIndicator
                    tone={row.status === "MATCH" ? "positive" : "warning"}
                    status={row.status}
                  />
                ),
              },
            ]}
          />
        )}
        {rows.length > visibleRows && (
          <Button
            className="mt-3"
            variant="outline"
            onClick={() => setVisibleRows((count) => count + 50)}
          >
            Show next 50 rows
          </Button>
        )}
      </PageSection>

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => setEvidenceOpen(true)}>
          Inspect source evidence
        </Button>
        <Button
          variant="outline"
          onClick={() => downloadLedgerJson(report, "ledger-preview.json")}
        >
          Download private report
        </Button>
      </div>
      <DetailDrawer
        open={evidenceOpen}
        onOpenChange={setEvidenceOpen}
        title="Ledger source and replay evidence"
      >
        <dl className="space-y-3 text-sm">
          {[
            ["Contract", report.contract_version],
            ["Projection", report.projection_version],
            ["Snapshot ID", report.anchor_snapshot_id],
            ["Anchor recorded", dateTime(report.anchor_recorded_at)],
            ["Booking cutoff", dateTime(report.as_of)],
            [
              "Ending observation",
              report.ending_statement_at
                ? dateTime(report.ending_statement_at)
                : "Not provided",
            ],
            ["Anchor SHA-256", report.anchor_sha256],
            ["Input SHA-256", report.input_sha256],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="break-all">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="my-4 text-xs text-muted-foreground">
          Source references identify documents for private review. The booking
          cutoff and anchor recording time describe different aspects of this
          reconstruction.
        </p>
        <details className="rounded-lg border p-3 text-sm">
          <summary className="cursor-pointer font-medium">
            Source records ({file.evidence.length})
          </summary>
          <ol className="mt-3 space-y-4">
            {file.evidence.map((proof, index) => (
              <li key={index} className="space-y-1 break-all text-xs">
                <p className="font-medium">
                  {proof.role} · {accountLabel(proof.accountId)}
                </p>
                <p>{proof.reference}</p>
                <p className="text-muted-foreground">{proof.sha256}</p>
              </li>
            ))}
          </ol>
        </details>
      </DetailDrawer>
    </div>
  );
}
