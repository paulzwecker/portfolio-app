"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { DetailDrawer } from "@/components/app/detail-drawer";
import { PendingOrError } from "@/components/app/empty-state";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanySecCoverage,
  type CompanySecCoverage,
} from "@/lib/domain-contracts";
import { dateOnly, dateTime, statusLabel } from "@/lib/display";

const mappingGuidance: Record<CompanySecCoverage["mapping_status"], string> = {
  MAPPED: "A reviewed SEC issuer identity is recorded.",
  UNMAPPED:
    "A reviewed SEC CIK mapping is required. International coverage may need another approved provider.",
  AMBIGUOUS:
    "Conflicting issuer mappings require operator review before SEC ingestion.",
  INVALID:
    "The issuer mapping has invalid identity evidence. Review it before SEC ingestion.",
};

function retainedTime(value: string | null) {
  return value ? dateTime(value) : "Not retained";
}

type SecRefresh = NonNullable<CompanySecCoverage["fundamentals"]["refresh"]>;
type SecIdentity = NonNullable<SecRefresh["identity"]>;
const issuerOutcomeLabels: Record<SecRefresh["issuer_outcome"], string> = {
  REPORTED: "Source response reported",
  DATA_CHECK: "Source response needs review",
  UNAVAILABLE: "No supported data in response",
  UNMAPPED: "Unmapped in this frozen scope",
  NOT_REPORTED: "No issuer-specific result recorded",
};

function identityGuidance(
  identity: SecIdentity | null | undefined,
  source: "refresh" | "bootstrap",
): string {
  switch (identity?.status) {
    case "MATCHED":
      return `${source === "refresh" ? "Refresh" : "Bootstrap"} issuer identity matches the current reviewed mapping; freshness is separate.`;
    case "CHANGED":
      return `Issuer mapping or recorded issuer details changed since this ${source}. Any result is historical, not evidence for the current identity.`;
    case "UNMAPPED_IN_SCOPE":
      return `This issuer was not mapped in the ${source} scope.`;
    case "CURRENT_UNAVAILABLE":
      return `Current reviewed issuer identity is unavailable; this historical ${source} cannot verify it.`;
    default:
      return `The ${source} issuer identity could not be verified from retained scope evidence.`;
  }
}

function SecRefreshDetails({
  refresh,
  filings,
}: {
  refresh: SecRefresh;
  filings: boolean;
}) {
  return (
    <section
      aria-label="Latest incremental refresh"
      className="space-y-2 border-t pt-3 text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-medium">Latest incremental refresh</h4>
        <StatusIndicator status={refresh.batch_status} />
      </div>
      <p className="text-xs text-muted-foreground">
        {statusLabel(refresh.trigger)} · {refresh.scope_company_count}{" "}
        {refresh.scope_company_count === 1 ? "company" : "companies"} in frozen
        scope
        {refresh.mapped_company_count !== null &&
          ` · ${refresh.mapped_company_count} mapped SEC ${refresh.mapped_company_count === 1 ? "issuer" : "issuers"}`}
      </p>
      <p>Issuer result · {issuerOutcomeLabels[refresh.issuer_outcome]}</p>
      <p
        className={
          refresh.identity?.status === "MATCHED"
            ? "text-xs text-muted-foreground"
            : "text-sm text-warning"
        }
      >
        {identityGuidance(refresh.identity, "refresh")}
        {refresh.identity?.frozen_cik &&
          ` Frozen refresh CIK ${refresh.identity.frozen_cik}.`}
      </p>
      {refresh.source_record_count !== null && (
        <p>
          {filings
            ? "Supported filing rows in result"
            : "Source facts in result"}{" "}
          · {refresh.source_record_count}
        </p>
      )}
      {refresh.issuer_outcome === "NOT_REPORTED" && (
        <p className="text-xs text-muted-foreground">
          The saved batch has no attributable outcome for this issuer. Retained
          evidence remains available above.
        </p>
      )}
      <dl className="grid gap-2 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Refresh requested</dt>
          <dd>{dateTime(refresh.requested_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Latest attempt started</dt>
          <dd>{dateTime(refresh.started_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Refresh finished</dt>
          <dd>{dateTime(refresh.finished_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Recorded attempts in run</dt>
          <dd>{refresh.attempt_count}</dd>
        </div>
      </dl>
      {refresh.failure_code && (
        <p className="break-words text-warning">
          Failure code · {refresh.failure_code}
        </p>
      )}
      {refresh.retryable && (
        <p className="text-xs text-muted-foreground">
          Last recorded attempt is retryable. Review Operations for cooldowns,
          remaining budget and authorized execution.
        </p>
      )}
      <p className="break-all text-xs text-muted-foreground">
        Run {refresh.run_id}
      </p>
      {refresh.request_id && (
        <p className="break-all text-xs text-muted-foreground">
          Manual request {refresh.request_id}
        </p>
      )}
    </section>
  );
}

export function SecCoverageDetails({ data }: { data: CompanySecCoverage }) {
  return (
    <div className="space-y-6">
      <section aria-label="SEC issuer identity" className="space-y-2">
        <h3 className="text-sm font-semibold">Issuer identity</h3>
        <StatusIndicator status={data.mapping_status} />
        <p className="text-sm text-muted-foreground">
          {mappingGuidance[data.mapping_status]}
        </p>
        {data.cik && (
          <p className="text-sm">
            CIK {data.cik} · {data.provider_company_name}
          </p>
        )}
        {data.identity_evidence_url && (
          <SourceReference
            label="SEC identity evidence"
            href={data.identity_evidence_url}
          />
        )}
      </section>
      {(
        [
          ["fundamentals", "Reported fundamentals"],
          ["filings", "Filing metadata"],
        ] as const
      ).map(([key, title]) => {
        const domain = data[key];
        const attempt = domain.bootstrap;
        return (
          <section
            key={key}
            aria-label={title}
            className="space-y-3 rounded-md border p-3"
          >
            <h3 className="text-sm font-semibold">{title}</h3>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted-foreground">
                  Retained records
                </dt>
                <dd>{domain.record_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Flagged records
                </dt>
                <dd>{domain.data_check_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Latest economic period end
                </dt>
                <dd>
                  {domain.latest_period_end
                    ? dateOnly(domain.latest_period_end)
                    : "Not retained"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Latest filing date
                </dt>
                <dd>
                  {domain.latest_filed_at
                    ? dateOnly(domain.latest_filed_at)
                    : "Not retained"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Latest retained retrieval
                </dt>
                <dd>{retainedTime(domain.latest_retrieved_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Latest record time
                </dt>
                <dd>{retainedTime(domain.latest_recorded_at)}</dd>
              </div>
            </dl>
            {key === "fundamentals" && data.fundamental_identity_counts && (
              <div className="space-y-1 border-t pt-3 text-sm">
                <h4 className="font-medium">
                  Recorded issuer CIK on retained facts
                </h4>
                <p>
                  {data.fundamental_identity_counts.matching_cik} matching ·{" "}
                  {data.fundamental_identity_counts.other_cik} different ·{" "}
                  {data.fundamental_identity_counts.unverified} unverifiable
                </p>
                <p className="text-xs text-muted-foreground">
                  Counts compare saved observation and batch metadata with the
                  current reviewed CIK. They do not verify source bytes,
                  historical mapping, economic validity or freshness. Filing
                  records are separate.
                </p>
                {(data.fundamental_identity_counts.other_cik > 0 ||
                  data.fundamental_identity_counts.unverified > 0) && (
                  <p className="text-warning">
                    Review issuer attribution before relying on reported
                    financial statements.
                  </p>
                )}
              </div>
            )}
            {domain.refresh ? (
              <SecRefreshDetails
                refresh={domain.refresh}
                filings={key === "filings"}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                {domain.refresh === undefined
                  ? "Incremental refresh history is unavailable from this API version."
                  : "No incremental refresh recorded for this issuer."}
              </p>
            )}
            {attempt ? (
              <div className="space-y-2 border-t pt-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span>Latest bootstrap checkpoint</span>
                  <StatusIndicator status={attempt.status} />
                </div>
                <p className="text-xs text-muted-foreground">
                  Prepared {dateTime(attempt.prepared_at)} · Finished{" "}
                  {dateTime(attempt.finished_at)} ·{" "}
                  {attempt.provider_request_count} provider requests
                </p>
                <p
                  className={
                    attempt.identity?.status === "MATCHED"
                      ? "text-xs text-muted-foreground"
                      : "text-sm text-warning"
                  }
                >
                  {identityGuidance(attempt.identity, "bootstrap")}
                  {attempt.identity?.frozen_cik &&
                    ` Frozen bootstrap CIK ${attempt.identity.frozen_cik}.`}
                </p>
                {attempt.failure_code && (
                  <p className="break-words text-warning">
                    {attempt.failure_code}
                  </p>
                )}
                {attempt.retryable && (
                  <p>
                    Retryable checkpoint · Next attempt after{" "}
                    {dateTime(attempt.next_attempt_at)}. Execution requires an
                    authorized operator.
                  </p>
                )}
                <p className="break-all text-xs text-muted-foreground">
                  Run {attempt.run_id}
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No per-issuer bootstrap checkpoint recorded.
              </p>
            )}
          </section>
        );
      })}
      <section aria-label="Reported metric coverage" className="space-y-2">
        <h3 className="text-sm font-semibold">Reported metric coverage</h3>
        <p className="text-sm">
          {data.metrics_present.length} retained metric types ·{" "}
          {data.metrics_missing.length} absent
        </p>
        {data.metrics_missing.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Absent from retained SEC facts ·{" "}
            {data.metrics_missing.map(statusLabel).join(", ")}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Retained metrics include flagged history. Inspect Financials for
          selected values and conflicting evidence. Missing concepts remain
          unavailable.
        </p>
      </section>
      <p className="text-xs text-muted-foreground">
        Retrieval dates describe retained evidence. Fiscal periods and filing
        dates describe its economic coverage. Incremental refreshes describe
        saved execution outcomes; batch status and issuer result retain their
        separate meanings. Bootstrap checkpoints describe the scoped backfill
        runner.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" asChild>
          <Link href={`/company/${data.company_id}?view=financials`}>
            Open Financials
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link
            href={`/company/${data.company_id}?view=research#source-documents`}
          >
            Open filing sources
          </Link>
        </Button>
      </div>
    </div>
  );
}

export function CompanySecCoveragePanel({
  companyId,
  operations = false,
}: {
  companyId: string;
  operations?: boolean;
}) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/sec-coverage`,
    isCompanySecCoverage,
  );
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const data = state.data;
  useEffect(() => {
    if (data && window.location.hash === "#company-sec-coverage") {
      panel.current?.focus({ preventScroll: true });
      panel.current?.scrollIntoView({ block: "start" });
    }
  }, [data]);
  return (
    <Card
      ref={panel}
      id="company-sec-coverage"
      role="region"
      aria-label="SEC source coverage"
      tabIndex={-1}
      className="min-w-0 scroll-mt-5 shadow-none"
    >
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0 pb-3">
        <div className="min-w-0">
          <CardTitle className="text-sm">SEC source coverage</CardTitle>
          {operations && data && (
            <p className="mt-1 break-words text-sm text-muted-foreground">
              {data.company_name}
            </p>
          )}
        </div>
        {data && <StatusIndicator status={data.mapping_status} />}
      </CardHeader>
      <CardContent className="space-y-3">
        {!data ? (
          <>
            <PendingOrError {...state} />
            <p className="text-sm text-warning">
              Retained issuer attribution has not been checked. Review source
              identities before relying on reported statements.
            </p>
          </>
        ) : (
          <>
            <p className="text-sm">
              {data.metrics_present.length} reported metric types ·{" "}
              {data.filings.record_count} retained filings
            </p>
            <p className="text-xs text-muted-foreground">
              Retained counts can include earlier runs; the latest identity
              checks do not verify every historical record.
            </p>
            {!data.fundamental_identity_counts &&
              data.fundamentals.record_count > 0 && (
                <p className="text-sm text-warning">
                  This API version does not report retained issuer attribution.
                  Review source identities before relying on reported
                  statements.
                </p>
              )}
            {data.fundamental_identity_counts &&
              (data.fundamental_identity_counts.other_cik > 0 ||
                data.fundamental_identity_counts.unverified > 0) && (
                <p role="alert" className="text-sm text-warning">
                  Retained facts include different or unverifiable issuer CIK
                  metadata. Review attribution before relying on financial
                  statements.
                </p>
              )}
            <p className="text-xs text-muted-foreground">
              Latest fact retrieval{" "}
              {retainedTime(data.fundamentals.latest_retrieved_at)} · Latest
              filing retrieval {retainedTime(data.filings.latest_retrieved_at)}
            </p>
            {data.mapping_status !== "MAPPED" && (
              <p className="text-sm text-warning">
                {mappingGuidance[data.mapping_status]}
              </p>
            )}
            {(
              [
                ["fundamentals", "Fundamentals"],
                ["filings", "Filings"],
              ] as const
            ).map(([key, label]) => {
              const refresh = data[key].refresh;
              const checkpoint = data[key].bootstrap;
              const checkpointAt =
                checkpoint?.finished_at ??
                checkpoint?.started_at ??
                checkpoint?.prepared_at;
              const refreshAt = refresh?.finished_at ?? refresh?.started_at;
              if (
                refresh &&
                refreshAt &&
                (!checkpointAt ||
                  Date.parse(refreshAt) >= Date.parse(checkpointAt))
              )
                return (
                  <p
                    key={key}
                    className="flex flex-wrap items-center gap-x-2 gap-y-1 break-words text-sm"
                  >
                    <span>{label} refresh batch</span>
                    <StatusIndicator status={refresh.batch_status} />
                    <span className="text-muted-foreground">
                      {issuerOutcomeLabels[refresh.issuer_outcome]}
                    </span>
                    {refresh.identity?.status !== "MATCHED" && (
                      <span className="text-warning">
                        {identityGuidance(refresh.identity, "refresh")}
                      </span>
                    )}
                    {checkpoint &&
                      checkpoint.identity?.status !== "MATCHED" && (
                        <span className="text-warning">
                          Other recorded bootstrap:{" "}
                          {identityGuidance(checkpoint.identity, "bootstrap")}
                        </span>
                      )}
                  </p>
                );
              return checkpoint &&
                ([
                  "FAILED",
                  "BLOCKED",
                  "UNAVAILABLE",
                  "RUNNING",
                  "PENDING",
                ].includes(checkpoint.status) ||
                  checkpoint.identity?.status !== "MATCHED" ||
                  (refresh && refresh.identity?.status !== "MATCHED")) ? (
                <p key={key} className="break-words text-sm text-warning">
                  {label} bootstrap · {statusLabel(checkpoint.status)}
                  {checkpoint.failure_code
                    ? ` · ${checkpoint.failure_code}`
                    : ""}
                  {checkpoint.identity?.status !== "MATCHED" && (
                    <> · {identityGuidance(checkpoint.identity, "bootstrap")}</>
                  )}
                  {refresh && refresh.identity?.status !== "MATCHED" && (
                    <>
                      {" "}
                      · Other recorded refresh:{" "}
                      {identityGuidance(refresh.identity, "refresh")}
                    </>
                  )}
                </p>
              ) : null;
            })}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
                Inspect SEC coverage
              </Button>
              {!operations && (
                <Button variant="ghost" size="sm" asChild>
                  <Link
                    href={`/operations?company=${encodeURIComponent(companyId)}#company-sec-coverage`}
                  >
                    Open company data diagnostics
                  </Link>
                </Button>
              )}
            </div>
            <DetailDrawer
              open={open}
              onOpenChange={setOpen}
              title="SEC coverage and provenance"
              description={data.company_name}
            >
              <SecCoverageDetails data={data} />
            </DetailDrawer>
          </>
        )}
      </CardContent>
    </Card>
  );
}
