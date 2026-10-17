"use client";

import { DetailDrawer } from "@/components/app/detail-drawer";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import type {
  CompanyFinancialStatements,
  ConsensusEstimateObservation,
  ReportedFundamentalObservation,
  ResearchRevision,
} from "@/lib/domain-contracts";
import { dateOnly, dateTime, quantity } from "@/lib/display";
import { rowLabel, unitLabel } from "./financial-series";

export type FinancialCellSelection = { rowId: string; periodEnd: string };

function ReportedSource({
  item,
  selected,
}: {
  item: ReportedFundamentalObservation;
  selected: boolean;
}) {
  return (
    <article className="space-y-2 rounded-lg border p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="break-all tabular-nums">
          {quantity(item.value)} {item.currency ?? item.unit}
        </strong>
        <StatusIndicator status={item.data_quality} />
        {selected && (
          <span className="font-medium text-primary">Selected source</span>
        )}
      </div>
      <p>
        {item.provider_id} · {item.form ?? "Form unknown"} ·{" "}
        {item.revision_context.replaceAll("_", " ")}
      </p>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-muted-foreground">
        <dt>Economic period</dt>
        <dd>
          {item.period_start
            ? `${dateOnly(item.period_start)} – `
            : "Instant · "}
          {dateOnly(item.period_end)}
        </dd>
        <dt>Filing context</dt>
        <dd>
          FY{item.fiscal_year ?? "unknown"} · {item.fiscal_period ?? "unknown"}{" "}
          (source filing label)
        </dd>
        <dt>Taxonomy / concept</dt>
        <dd className="break-all">
          {item.source_taxonomy}:{item.source_concept}
        </dd>
        <dt>Source units</dt>
        <dd>
          {item.source_unit} · normalized {item.unit}
        </dd>
        <dt>Published / filed</dt>
        <dd>{dateTime(item.filed_at)}</dd>
        <dt>Observed</dt>
        <dd>{dateTime(item.observed_at)}</dd>
        <dt>Recorded</dt>
        <dd>{dateTime(item.recorded_at)}</dd>
        {item.supersedes_observation_id && (
          <>
            <dt>Supersedes</dt>
            <dd className="break-all">{item.supersedes_observation_id}</dd>
          </>
        )}
      </dl>
      {item.quality_reason && (
        <p className="text-warning">{item.quality_reason}</p>
      )}
      <SourceReference
        label="Filing / original evidence"
        href={item.source_url}
        reference={item.accession_number ?? item.source_ref}
      />
    </article>
  );
}

function ConsensusSource({ item }: { item: ConsensusEstimateObservation }) {
  return (
    <article className="space-y-2 rounded-lg border p-3 text-xs">
      <div className="flex flex-wrap gap-2">
        <strong className="tabular-nums">
          {quantity(item.value)} {item.currency ?? "currency unknown"} ·{" "}
          {item.unit}
        </strong>
        <StatusIndicator status={item.data_quality} />
      </div>
      <p>
        {item.provider_id} · {item.forecast_period} · ends{" "}
        {item.period_end ?? "unknown"}
      </p>
      <p>
        {item.analyst_count ?? "Unknown"} analysts · snapshot{" "}
        {item.snapshot_date} · {item.revision_context}
      </p>
      <p className="text-muted-foreground">
        Observed {dateTime(item.observed_at)} · recorded{" "}
        {dateTime(item.recorded_at)}
      </p>
      {item.supersedes_observation_id && (
        <p className="break-all">Supersedes {item.supersedes_observation_id}</p>
      )}
      {item.quality_reason && (
        <p className="text-warning">{item.quality_reason}</p>
      )}
      <SourceReference
        label="Consensus source"
        href={item.source_ref.startsWith("https://") ? item.source_ref : null}
        reference={item.source_ref}
      />
    </article>
  );
}

function ResearchSource({
  revision,
  ids,
}: {
  revision: ResearchRevision;
  ids?: string[];
}) {
  return (
    <article className="space-y-3 rounded-lg border p-3 text-xs">
      <div className="flex flex-wrap gap-2">
        <strong>
          {revision.author_id} · revision {revision.revision_number}
        </strong>
        <StatusIndicator status={revision.status} />
      </div>
      <p className="break-all text-muted-foreground">
        {revision.id} · external {revision.external_revision_id}
      </p>
      <p>{revision.rationale}</p>
      <p className="text-muted-foreground">
        Observed {dateTime(revision.observed_at)} · recorded{" "}
        {dateTime(revision.recorded_at)}
      </p>
      <SourceReference
        label={revision.source_id}
        href={
          revision.source_reference.startsWith("https://")
            ? revision.source_reference
            : null
        }
        reference={revision.source_reference}
      />
      {revision.supersedes_revision_id && (
        <p className="break-all">
          Supersedes revision {revision.supersedes_revision_id}
        </p>
      )}
      {revision.forecasts
        .filter((f) => !ids || ids.includes(f.id))
        .map((forecast) => (
          <div key={forecast.id} className="border-l-2 pl-3">
            <p className="font-medium">
              {forecast.metric} · FY{forecast.fiscal_year}{" "}
              {forecast.fiscal_period} · {forecast.scenario}
            </p>
            <p className="tabular-nums">
              {quantity(forecast.value)} {forecast.currency ?? forecast.unit} ·{" "}
              {forecast.availability_status}
            </p>
            <p>
              Period end {forecast.period_end ?? "not supplied"} ·{" "}
              {forecast.unit} · {forecast.confidence} confidence
            </p>
            {forecast.rationale && <p>{forecast.rationale}</p>}
            {forecast.uncertainty && (
              <p>Uncertainty · {forecast.uncertainty}</p>
            )}
            {forecast.availability_reason && (
              <p>{forecast.availability_reason}</p>
            )}
          </div>
        ))}
      {revision.evidence.map((item) => (
        <SourceReference
          key={item.id}
          label={item.source_name}
          href={item.source_url}
          reference={item.external_identifier ?? item.source_document_title}
        />
      ))}
      {revision.assessments.length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">
            Qualitative assessments ({revision.assessments.length})
          </summary>
          {revision.assessments.map((item) => (
            <p className="mt-2" key={item.id}>
              {item.assessment_type} · {item.status} · {item.confidence} ·{" "}
              {item.narrative ?? item.status_reason ?? "No narrative"}
            </p>
          ))}
        </details>
      )}
    </article>
  );
}

export function FinancialSourceDrawer({
  data,
  selection,
  open,
  onOpenChange,
}: {
  data: CompanyFinancialStatements;
  selection: FinancialCellSelection | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const row = data.rows.find((item) => item.id === selection?.rowId);
  const cell = row?.cells.find(
    (item) => item.period_end === selection?.periodEnd,
  );
  const ids = cell?.source_ids ?? [];
  const facts = data.reported_periods
    .flatMap((period) => period.observations)
    .filter((item) => ids.includes(item.id));
  const consensus = data.consensus.providers
    .flatMap((provider) => provider.periods.flatMap((period) => period.history))
    .filter((item) => ids.includes(item.id));
  const research = data.research.streams
    .flatMap((stream) => stream.history)
    .filter((revision) => revision.forecasts.some((f) => ids.includes(f.id)));
  return (
    <DetailDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={
        row
          ? `${row.label} · ${cell?.period_end ?? ""}`
          : "Financial sources & limitations"
      }
      description={
        row
          ? rowLabel(row)
          : "Canonical source coverage, alignment checks and revision archives."
      }
    >
      <div className="space-y-4">
        {cell && row ? (
          <>
            <div className="rounded-lg bg-muted/40 p-3">
              <p className="break-all text-lg font-semibold tabular-nums">
                {cell.value === null ? "Unavailable" : quantity(cell.value)}{" "}
                {unitLabel(row)}
              </p>
              <StatusIndicator status={cell.status} />
              {cell.reason && <p className="mt-2 text-sm">{cell.reason}</p>}
            </div>
            <p className="text-xs text-muted-foreground">
              Latest eligible source selected within the requested publication
              and app-knowledge cutoffs. Original filing context labels below
              are retained as provenance, not treated as distinct financial
              periods.
            </p>
            {facts.map((item) => (
              <ReportedSource
                key={item.id}
                item={item}
                selected={item.id === cell.selected_source_id}
              />
            ))}
            {consensus.map((item) => (
              <ConsensusSource key={item.id} item={item} />
            ))}
            {research.map((revision) => (
              <ResearchSource key={revision.id} revision={revision} ids={ids} />
            ))}
          </>
        ) : (
          <>
            <h3 className="text-sm font-semibold">Availability & alignment</h3>
            <ul className="space-y-3 text-sm">
              {data.limitations.map((item, i) => (
                <li
                  key={`${item.reference_id ?? item.source_name}-${i}`}
                  className="border-l-2 pl-3"
                >
                  <p className="font-medium">{item.source_name}</p>
                  <p className="mt-1 text-muted-foreground">{item.reason}</p>
                </li>
              ))}
            </ul>
            <a
              href={`/company/${data.company_id}?view=valuation`}
              className="inline-block text-sm text-primary underline"
            >
              Inspect accepted model projections in Valuation
            </a>
            <h3 className="border-t pt-4 text-sm font-semibold">
              Consensus source archive
            </h3>
            <p className="text-xs text-muted-foreground">
              {data.consensus.continuity_status.replaceAll("_", " ")} · selected
              provider {data.consensus.selected_provider_id ?? "none"}.
              Providers are never blended.
            </p>
            {!data.consensus.providers.length && (
              <p className="text-sm">No consensus provider mapping.</p>
            )}
            {data.consensus.providers.map((provider) => (
              <details
                key={`${provider.provider_id}-${provider.role}`}
                className="rounded-lg border p-3"
              >
                <summary className="cursor-pointer text-sm font-medium">
                  {provider.provider_id} · {provider.role} ·{" "}
                  {provider.freshness} · {provider.observation_count}{" "}
                  observations
                </summary>
                <p className="my-2 text-xs">
                  {provider.provider_symbol} ·{" "}
                  {provider.currency ?? "currency unknown"} ·{" "}
                  {provider.identity_evidence_source}
                </p>
                <div className="space-y-2">
                  {provider.periods
                    .flatMap((period) => period.history)
                    .map((item) => (
                      <ConsensusSource key={item.id} item={item} />
                    ))}
                </div>
              </details>
            ))}
            <h3 className="border-t pt-4 text-sm font-semibold">
              Accepted agent research archive
            </h3>
            {!data.research.streams.length && (
              <p className="text-sm text-muted-foreground">
                No accepted agent forecasts or assessments. Research is distinct
                from analyst consensus and model assumptions.
              </p>
            )}
            {data.research.streams.map((stream) => (
              <details
                key={stream.stream_key}
                className="rounded-lg border p-3"
              >
                <summary className="cursor-pointer text-sm font-medium">
                  {stream.stream_key} · {stream.history.length} revisions
                </summary>
                <div className="mt-3 space-y-3">
                  {stream.history.map((revision) => (
                    <ResearchSource key={revision.id} revision={revision} />
                  ))}
                </div>
              </details>
            ))}
          </>
        )}
      </div>
    </DetailDrawer>
  );
}
