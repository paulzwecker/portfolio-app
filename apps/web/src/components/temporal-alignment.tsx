"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isCompanyTemporalAlignment,
  type CompanyTemporalAlignment,
  type TemporalAlignedValue,
  type TemporalModelForecast,
} from "@/lib/domain-contracts";
import { date, percent, quantity } from "@/lib/display";

function currentDate() {
  return new Date().toISOString().slice(0, 10);
}

function amount(value: string | null, currency: string | null) {
  if (value === null) return "Unavailable";
  return `${currency ?? "Currency unknown"} ${quantity(value)}`;
}

function dateLabel(value: string | null) {
  return value ? date(value) : "Not recorded";
}

function SourceReference({ value }: { value: string | null }) {
  if (!value) return <span>Source reference unavailable</span>;
  if (/^https:\/\//i.test(value))
    return (
      <a
        className="break-all underline underline-offset-2 hover:text-foreground"
        href={value}
        target="_blank"
        rel="noreferrer"
      >
        Open source
      </a>
    );
  return <span className="break-all">{value}</span>;
}

function ValueCard({
  title,
  value,
  note,
}: {
  title: string;
  value: TemporalAlignedValue;
  note?: string;
}) {
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">{title}</CardTitle>
          <Badge
            variant={value.status === "AVAILABLE" ? "outline" : "secondary"}
          >
            {value.status.replaceAll("_", " ")}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="break-words text-xl font-semibold tabular-nums">
          {amount(value.value, value.currency)}
        </p>
        <p className="text-xs text-muted-foreground">
          {value.unit ?? "Unit unavailable"}
          {value.period_end
            ? ` · period ended ${dateLabel(value.period_end)}`
            : ""}
        </p>
        {value.low_value !== undefined && value.low_value !== null && (
          <p className="text-xs text-muted-foreground">
            Consensus range · {quantity(value.low_value)} to{" "}
            {value.high_value === null || value.high_value === undefined
              ? "unknown"
              : quantity(value.high_value)}
            {value.analyst_count === null || value.analyst_count === undefined
              ? " · coverage unknown"
              : ` · ${value.analyst_count} analysts`}
          </p>
        )}
        <p className="text-xs leading-5 text-muted-foreground">
          {title === "Actual"
            ? `Filed/effective ${dateLabel(value.effective_at)} · observed ${dateLabel(value.observed_at)} · recorded ${dateLabel(value.recorded_at)}`
            : `Effective ${dateLabel(value.effective_at)} · observed ${dateLabel(value.observed_at)} · recorded ${dateLabel(value.recorded_at)}`}
          {value.source_name
            ? ` · ${value.source_name}`
            : " · source unavailable"}
        </p>
        <p className="text-xs leading-5 text-muted-foreground">
          <SourceReference value={value.source_reference} />
        </p>
        {value.quality_reason && (
          <p className="rounded-md border border-dashed p-2 text-xs leading-5 text-muted-foreground">
            {value.quality_reason}
          </p>
        )}
        {note && (
          <p className="text-xs leading-5 text-muted-foreground">{note}</p>
        )}
      </CardContent>
    </Card>
  );
}

function ModelForecastCard({
  model,
  fiscalYear,
}: {
  model: TemporalModelForecast;
  fiscalYear: number;
}) {
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">{model.model_name}</CardTitle>
          <Badge
            variant={model.status === "AVAILABLE" ? "outline" : "secondary"}
          >
            {model.status.replaceAll("_", " ")}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="break-words text-xl font-semibold tabular-nums">
          {amount(model.value, model.model_currency)}
        </p>
        {model.status === "FISCAL_YEAR_MAPPING_UNAVAILABLE" && (
          <p className="text-xs leading-5 text-muted-foreground">
            FY{fiscalYear} cannot be assigned: this revision stores ordinal
            projection years without a fiscal-year anchor. Revision{" "}
            {model.revision_number ?? "unknown"} remains selected at the cutoff.
          </p>
        )}
        <p className="text-xs leading-5 text-muted-foreground">
          Base-scenario revenue · forecast year{" "}
          {model.forecast_year ?? "unavailable"} · revision{" "}
          {model.revision_number ?? "unknown"}
        </p>
        <p className="text-xs leading-5 text-muted-foreground">
          Effective {dateLabel(model.effective_at)} · recorded{" "}
          {dateLabel(model.recorded_at)}
          {model.revision_source ? ` · ${model.revision_source}` : ""}
        </p>
        {model.rationale && (
          <p className="rounded-md border border-dashed p-2 text-xs leading-5 text-muted-foreground">
            {model.rationale}
          </p>
        )}
        <div className="grid gap-3 border-t pt-3 sm:grid-cols-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-medium">Price at forecast</p>
              <Badge variant="secondary">
                {model.price_at_forecast.status.replaceAll("_", " ")}
              </Badge>
            </div>
            {model.price_at_forecast.close === null ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {model.price_at_forecast.status.replaceAll("_", " ")} ·{" "}
                {model.price_at_forecast.reason ??
                  "No eligible exact-listing close."}
              </p>
            ) : (
              <>
                <p className="mt-1 break-words text-sm font-semibold tabular-nums">
                  {amount(
                    model.price_at_forecast.close,
                    model.price_at_forecast.currency,
                  )}
                </p>
                <p className="text-xs leading-5 text-muted-foreground">
                  {model.price_at_forecast.listing?.ticker ?? "Listing unknown"}{" "}
                  · {dateLabel(model.price_at_forecast.market_date)} ·{" "}
                  {model.price_at_forecast.listing?.venue ?? ""} ·{" "}
                  {model.price_at_forecast.provider ?? "Provider unknown"} ·{" "}
                  {model.price_at_forecast.data_quality ?? "quality unknown"}
                </p>
              </>
            )}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-medium">Subsequent total return</p>
              <Badge variant="secondary">
                {model.subsequent_market_return.status.replaceAll("_", " ")}
              </Badge>
            </div>
            {model.subsequent_market_return.return_fraction === null ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {model.subsequent_market_return.status.replaceAll("_", " ")} ·{" "}
                {model.subsequent_market_return.reason ??
                  "Outcome unavailable."}
              </p>
            ) : (
              <>
                <p className="mt-1 text-sm font-semibold tabular-nums">
                  {percent(model.subsequent_market_return.return_fraction)}
                </p>
                <p className="text-xs leading-5 text-muted-foreground">
                  {dateLabel(model.subsequent_market_return.start_market_date)}{" "}
                  to {dateLabel(model.subsequent_market_return.end_market_date)}{" "}
                  · target{" "}
                  {dateLabel(model.subsequent_market_return.target_date)}
                </p>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AlignmentContent({ data }: { data: CompanyTemporalAlignment }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
        Forecast cutoff {date(data.forecast_known_at)}. Later actuals are shown
        only as outcomes known by {date(data.outcome_known_at)}. Fiscal-year
        mapping: {data.fiscal_year_mapping_basis.replaceAll("_", " ")}.
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {data.model_forecasts.length ? (
          data.model_forecasts.map((model) => (
            <ModelForecastCard
              key={model.model_id}
              model={model}
              fiscalYear={data.fiscal_year}
            />
          ))
        ) : (
          <Card className="shadow-none md:col-span-3">
            <CardContent className="py-5 text-sm text-muted-foreground">
              No canonical model forecast is available at this cutoff.
            </CardContent>
          </Card>
        )}
        <ValueCard
          title="Consensus"
          value={data.consensus}
          note="Selected continuity provider only; providers are not blended."
        />
        <ValueCard
          title="Actual"
          value={data.actual}
          note="Reported facts are resolved using the outcome cutoff, never the forecast cutoff."
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Comparison state · {data.comparison_status.replaceAll("_", " ")}. Values
        are not scored or ranked.
      </p>
    </div>
  );
}

export function TemporalAlignment({ companyId }: { companyId: string }) {
  const [asOf, setAsOf] = useState(currentDate);
  const [fiscalYear, setFiscalYear] = useState(
    String(new Date().getUTCFullYear() + 1),
  );
  const [horizonDays, setHorizonDays] = useState("365");
  const requestPath = `companies/${encodeURIComponent(companyId)}/temporal-alignment?fiscal_year=${encodeURIComponent(fiscalYear)}&as_of=${encodeURIComponent(asOf)}&horizon_days=${encodeURIComponent(horizonDays)}`;
  const state = useResearch(requestPath, isCompanyTemporalAlignment);

  return (
    <section
      id="temporal-alignment"
      aria-labelledby="temporal-alignment-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="temporal-alignment-title" className="text-xl font-semibold">
            Forecast vs. outcome
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
            Point-in-time revenue forecast, selected consensus, reported actual
            and exact-listing market outcome.
          </p>
        </div>
        <div className="grid w-full grid-cols-2 gap-2 sm:w-auto sm:grid-cols-3">
          <label className="grid gap-1 text-xs text-muted-foreground">
            Fiscal year
            <input
              aria-label="Fiscal year"
              className="h-9 min-w-0 rounded-md border bg-background px-2 text-sm text-foreground"
              type="number"
              min="1800"
              max="2200"
              value={fiscalYear}
              onChange={(event) => setFiscalYear(event.target.value)}
            />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            Forecast date
            <input
              aria-label="Forecast date"
              className="h-9 min-w-0 rounded-md border bg-background px-2 text-sm text-foreground"
              type="date"
              value={asOf}
              onChange={(event) => setAsOf(event.target.value)}
            />
          </label>
          <label className="col-span-2 grid gap-1 text-xs text-muted-foreground sm:col-span-1">
            Return horizon
            <select
              aria-label="Return horizon"
              className="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
              value={horizonDays}
              onChange={(event) => setHorizonDays(event.target.value)}
            >
              <option value="90">90 days</option>
              <option value="180">180 days</option>
              <option value="365">1 year</option>
              <option value="730">2 years</option>
            </select>
          </label>
        </div>
      </div>
      {!state.data ? (
        <PendingOrError {...state} />
      ) : (
        <AlignmentContent data={state.data} />
      )}
      <div className="mt-3 flex justify-end">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setAsOf(currentDate());
            setFiscalYear(String(new Date().getUTCFullYear() + 1));
          }}
        >
          Reset to current date
        </Button>
      </div>
    </section>
  );
}
