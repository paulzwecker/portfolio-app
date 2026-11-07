import { ResponsiveDataTable } from "@/components/app/responsive-data-table";
import { StatusIndicator } from "@/components/app/status-indicator";
import type { GoogleSheetsSyncCandidate } from "@/lib/domain-contracts";
import { dateTime, quantity } from "@/lib/display";

const labels = {
  bear_fv: "Bear",
  base_fv: "Base",
  bull_fv: "Bull",
  weighted_fv: "Weighted",
};

export function ModelPublicationReview({
  candidate,
}: {
  candidate: Pick<
    GoogleSheetsSyncCandidate,
    "publication" | "model_currency" | "previewed_at" | "preview_fingerprint"
  >;
}) {
  const evidence = candidate.publication;
  if (!evidence) return null;
  return (
    <section
      aria-label="Published model calculation check"
      className="space-y-3 rounded-md border p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">Source calculation check</h4>
        <StatusIndicator
          tone={evidence.parity_status === "MATCH" ? "positive" : "warning"}
          label={
            evidence.parity_status === "MATCH"
              ? "Values match"
              : evidence.parity_status === "MISMATCH"
                ? "Values differ"
                : "Calculation unavailable"
          }
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Fair value in {candidate.model_currency ?? "unresolved currency"} per
        listing share. Differences are native minus published, with absolute
        tolerance {quantity(evidence.absolute_tolerance)}.
      </p>
      <ResponsiveDataTable
        caption="Published and native fair values"
        rows={evidence.comparisons}
        getRowKey={(row) => row.field}
        columns={[
          {
            id: "scenario",
            header: "Scenario",
            render: (row) => labels[row.field],
          },
          {
            id: "published",
            header: "Published",
            render: (row) => (
              <span className="break-all font-mono text-xs tabular-nums">
                {quantity(row.published_value)}
              </span>
            ),
          },
          {
            id: "native",
            header: "Native",
            render: (row) => (
              <span className="break-all font-mono text-xs tabular-nums">
                {row.native_value === null
                  ? "Unavailable"
                  : quantity(row.native_value)}
              </span>
            ),
          },
          {
            id: "difference",
            header: "Difference",
            render: (row) => (
              <span className="break-all font-mono text-xs tabular-nums">
                {row.difference === null
                  ? "Unavailable"
                  : quantity(row.difference)}
              </span>
            ),
          },
          {
            id: "result",
            header: "Check",
            render: (row) =>
              row.matches === null
                ? "Unavailable"
                : row.matches
                  ? "Match"
                  : "Mismatch",
          },
        ]}
      />
      <p className="text-xs text-muted-foreground">
        Numerical agreement supports calculation reproducibility. The reviewer
        evaluates assumptions, evidence and return methodology before
        acceptance.
      </p>
      <details className="rounded-md border p-3 text-xs">
        <summary className="cursor-pointer font-medium">
          Publication identity and review context
        </summary>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Source published</dt>
            <dd>{dateTime(evidence.published_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Preview calculated</dt>
            <dd>{dateTime(candidate.previewed_at)}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-muted-foreground">Frozen contract SHA-256</dt>
            <dd className="mt-1 break-all font-mono">
              {evidence.contract_sha256}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-muted-foreground">Reviewed preview SHA-256</dt>
            <dd className="mt-1 break-all font-mono">
              {candidate.preview_fingerprint ?? "Unavailable"}
            </dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
