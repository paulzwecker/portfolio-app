"use client";

import { useState, type FormEvent } from "react";
import { PendingOrError } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { ResponsiveDataTable } from "@/components/app/responsive-data-table";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  dateTime,
  formatCurrency,
  formatPercent,
  statusLabel,
} from "@/lib/display";
import {
  hypotheticalEntryPrice,
  isReturnHurdle,
  matchesReturnHurdleRequest,
  requiredReturnFromPercent,
  type ReturnHurdle,
} from "@/lib/return-hurdle-contracts";

const changedRevision =
  "The accepted model changed. Reload the company before calculating a return hurdle.";

export function ReturnHurdleResult({ data }: { data: ReturnHurdle }) {
  const money = (value: string | null) =>
    formatCurrency(value, data.model_currency, 2, "Unavailable");
  const rate = (value: string | null) => formatPercent(value, 2, "Unavailable");
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="outline">
          {data.return_methodology.perspective === "ENTERPRISE"
            ? "Enterprise return basis"
            : "Equity return basis"}
        </Badge>
        <span>
          {data.ticker} · {data.venue} · {data.model_currency}
        </span>
        <StatusIndicator status={data.status} />
      </div>
      <p className="text-sm leading-6 text-muted-foreground">
        {data.return_methodology.title}. {data.return_methodology.limitation}
      </p>
      <div className="grid min-w-0 gap-3 md:grid-cols-2">
        <MetricCard
          label="Model entry price at selected return"
          value={money(data.weighted_entry_price)}
          note={`Selected annual return ${rate(data.required_return)} · probability-weighted accepted cash flows.`}
          detail={
            data.unavailable_reason ??
            "A hypothetical valuation reference, not a trade instruction or a forecast of the market price."
          }
        />
        {data.hypothetical_status !== "NOT_REQUESTED" ? (
          <MetricCard
            label="Modeled return at your entry price"
            value={rate(data.hypothetical_expected_irr)}
            note={`Hypothetical entry ${money(data.hypothetical_entry_price)} · ${data.return_methodology.perspective === "ENTERPRISE" ? "enterprise" : "equity"} cash-flow IRR.`}
            detail={
              data.hypothetical_unavailable_reason ??
              "Accepted operating cash flows, terminal assumptions and probabilities remain fixed."
            }
          />
        ) : (
          <MetricCard
            label="Accepted model hurdle"
            value={rate(data.accepted_hurdle)}
            note="Recorded model context. Your selected return is temporary and does not replace this assumption."
            detail={`Accepted revision ${data.revision_number} · ${data.methodology_version}`}
          />
        )}
      </div>
      <ResponsiveDataTable
        caption="Scenario entry prices at the same selected return"
        rows={data.scenarios}
        getRowKey={(row) => row.scenario}
        columns={[
          {
            id: "scenario",
            header: "Accepted scenario",
            render: (row) => (
              <span className="font-medium">{statusLabel(row.scenario)}</span>
            ),
          },
          {
            id: "probability",
            header: "Accepted probability",
            render: (row) => rate(row.probability),
          },
          {
            id: "price",
            header: `Model entry price · ${data.model_currency}`,
            render: (row) => (
              <span className="tabular-nums">
                {money(row.required_entry_price)}
              </span>
            ),
          },
          {
            id: "status",
            header: "Calculation",
            render: (row) => (
              <>
                <StatusIndicator status={row.status} />
                {row.unavailable_reason && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {row.unavailable_reason}
                  </p>
                )}
              </>
            ),
          },
        ]}
      />
      <p className="text-xs leading-5 text-muted-foreground">
        Each scenario uses the same selected return. The combined entry price
        follows the accepted probability-weighted cash flows; it is not an
        average of scenario IRRs. A lower selected return is a different
        constraint, not better company economics.
      </p>
      {data.contributions && (
        <div className="rounded-md border bg-muted/25 p-4">
          <h4 className="text-sm font-semibold">
            What supports the entry value?
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Amounts per share, discounted at your selected return. Terminal
            proceeds retain the accepted model assumptions.
          </p>
          <dl className="mt-3 grid gap-3 sm:grid-cols-3">
            {[
              [
                "Years 1–10 cash flows",
                data.contributions.annual_cash_flow_pv_per_share,
              ],
              ["Terminal proceeds", data.contributions.terminal_pv_per_share],
              [
                "Opening balance-sheet bridge",
                data.contributions.opening_balance_sheet_per_share,
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 font-semibold tabular-nums">
                  {money(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      {data.current_price !== null ? (
        <div className="space-y-2 rounded-md border p-4 text-sm">
          <h4 className="font-semibold">Observed market context</h4>
          <dl className="grid gap-3 sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">
                Observed model-reference price
              </dt>
              <dd className="mt-1 tabular-nums">{money(data.current_price)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">
                Modeled IRR at that price
              </dt>
              <dd className="mt-1 tabular-nums">
                {rate(data.current_expected_irr)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">
                Required entry value / observed price − 1
              </dt>
              <dd className="mt-1 tabular-nums">
                {rate(data.current_price_gap_to_required)}
              </dd>
            </div>
          </dl>
          <p className="text-xs text-muted-foreground">
            {data.market_price.provider ?? "Provider not recorded"} · effective{" "}
            {data.market_price.effective_at
              ? dateTime(data.market_price.effective_at)
              : "unavailable"}
            .{" "}
            {data.market_price.adjustment_basis ??
              "Adjustment basis not recorded"}
            . This comparison is valuation context, not expected price
            appreciation.
          </p>
          <SourceReference
            label="Price observation"
            reference={data.market_price.observation_id}
          />
        </div>
      ) : (
        <p
          role="status"
          className="rounded-md border border-warning/30 bg-warning/5 p-3 text-xs leading-5"
        >
          Observed market comparison unavailable ·{" "}
          {statusLabel(data.market_price.status)}.{" "}
          {data.market_price.reason ??
            "A fresh, matching price is required; no market price has been invented."}{" "}
          The hypothetical calculation uses accepted model inputs only.
        </p>
      )}
      <details className="rounded-md border p-4 text-xs">
        <summary className="cursor-pointer font-semibold">
          Method, cash flows and source evidence
        </summary>
        <div className="mt-3 space-y-4">
          <p className="leading-5">
            {data.return_methodology.cash_flow_basis} Entry basis:{" "}
            {data.return_methodology.entry_value_basis} Share-price basis:{" "}
            {data.return_methodology.share_price_basis}
          </p>
          <p className="leading-5">
            The selected return discounts the accepted modeled cash flows. It
            does not change WACC, cost of equity, terminal growth, terminal
            value inputs or scenario probabilities. Forecast years below are
            model ordinals, not mapped fiscal periods or reported actuals.
          </p>
          <ResponsiveDataTable
            caption="Accepted probability-weighted modeled cash flows per share"
            rows={data.cash_flows}
            getRowKey={(row) => String(row.forecast_year)}
            columns={[
              {
                id: "year",
                header: "Model year",
                render: (row) => row.forecast_year,
              },
              {
                id: "annual",
                header: `Annual cash flow · ${data.model_currency}`,
                render: (row) => money(row.annual_cash_flow_per_share),
              },
              {
                id: "terminal",
                header: `Terminal proceeds · ${data.model_currency}`,
                render: (row) => money(row.terminal_cash_flow_per_share),
              },
            ]}
          />
          <p>
            Accepted revision {data.revision_number} · effective{" "}
            {dateTime(data.effective_at)} · recorded{" "}
            {dateTime(data.recorded_at)}. Calculated{" "}
            {dateTime(data.calculated_at)}.
          </p>
          <SourceReference
            label={data.source ?? "Accepted model source not recorded"}
            reference={data.revision_id}
          />
          <p className="break-all text-muted-foreground">
            {data.calculation_version} · {data.methodology_version} · model{" "}
            {data.model_id}
          </p>
        </div>
      </details>
    </div>
  );
}

export function ReturnHurdleExplorer({
  companyId,
  modelId,
  revisionId,
  listingId,
  currency,
}: {
  companyId: string;
  modelId: string;
  revisionId: string;
  listingId: string;
  currency: string;
}) {
  const [open, setOpen] = useState(false);
  const [requiredPercent, setRequiredPercent] = useState("");
  const [priceInput, setPriceInput] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<{
    requiredPercent: string;
    priceInput: string;
    requiredReturn: string;
    entryPrice: string | null;
  } | null>(null);
  const params = new URLSearchParams({ base_revision_id: revisionId });
  if (submitted) params.set("required_return", submitted.requiredReturn);
  if (submitted?.entryPrice) params.set("entry_price", submitted.entryPrice);
  const unchanged =
    submitted?.requiredPercent === requiredPercent &&
    submitted.priceInput === priceInput;
  const state = useResearch(
    `financial-models/${modelId}/return-hurdle?${params}`,
    isReturnHurdle,
    0,
    open && !!submitted && unchanged,
    changedRevision,
  );
  const identityError =
    state.data &&
    (!matchesReturnHurdleRequest(state.data, {
      modelId,
      revisionId,
      requiredReturn: submitted!.requiredReturn,
      entryPrice: submitted!.entryPrice,
    }) ||
      state.data.company_id !== companyId ||
      state.data.valuation_listing_id !== listingId ||
      state.data.model_currency !== currency)
      ? "The result does not match the selected company, model, listing, currency or inputs. Reload the company before continuing."
      : null;
  const run = (event: FormEvent) => {
    event.preventDefault();
    const requiredReturn = requiredReturnFromPercent(requiredPercent);
    const entryPrice = priceInput.trim()
      ? hypotheticalEntryPrice(priceInput)
      : null;
    if (requiredReturn === null || (priceInput.trim() && entryPrice === null)) {
      setInputError(
        requiredReturn === null
          ? "Enter an annual return from 0 up to, but not including, 100%, using a decimal point and at most eight decimal places."
          : "Enter a positive price using a decimal point, up to 18 integer digits and ten decimal places, or leave it blank.",
      );
      return;
    }
    setInputError(null);
    setSubmitted({ requiredPercent, priceInput, requiredReturn, entryPrice });
    if (
      submitted?.requiredReturn === requiredReturn &&
      submitted.entryPrice === entryPrice
    )
      state.retry();
  };
  return (
    <Card
      className="min-w-0 border-primary/20 shadow-none"
      role="region"
      aria-label="Return hurdle explorer"
    >
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <CardTitle role="heading" aria-level={3} className="text-base">
            What entry price supports your required return?
          </CardTitle>
          <Badge variant="outline">Hypothetical · read-only</Badge>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Explore the accepted model’s cash flows at a return you specify.
            Assumptions, valuations and investment decisions are not saved or
            changed.
          </p>
        </div>
        <Button
          variant="outline"
          className="min-h-11 shrink-0"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "Close explorer" : "Explore required return"}
        </Button>
      </CardHeader>
      {open && (
        <CardContent className="space-y-5">
          <form onSubmit={run} className="space-y-3">
            <div className="grid min-w-0 gap-3 sm:grid-cols-2">
              <label className="grid min-w-0 gap-2 text-sm font-medium">
                Required annual return (%)
                <input
                  aria-label="Required annual return (%)"
                  inputMode="decimal"
                  value={requiredPercent}
                  onChange={(event) => {
                    setRequiredPercent(event.target.value);
                    setInputError(null);
                  }}
                  className="min-h-11 min-w-0 rounded-md border bg-background px-3 tabular-nums"
                  required
                  autoComplete="off"
                />
              </label>
              <label className="grid min-w-0 gap-2 text-sm font-medium">
                Hypothetical entry price ({currency}, optional)
                <input
                  aria-label={`Hypothetical entry price (${currency}, optional)`}
                  inputMode="decimal"
                  value={priceInput}
                  onChange={(event) => {
                    setPriceInput(event.target.value);
                    setInputError(null);
                  }}
                  className="min-h-11 min-w-0 rounded-md border bg-background px-3 tabular-nums"
                  autoComplete="off"
                />
              </label>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              Enter a percentage, not a decimal ratio. Leave entry price blank
              to calculate only the model entry value. No current market price
              is required.
            </p>
            <Button type="submit" className="min-h-11">
              Calculate entry value
            </Button>
            {inputError && (
              <p role="alert" className="text-sm text-warning">
                {inputError}
              </p>
            )}
          </form>
          {submitted && !unchanged && (
            <p role="status" className="text-sm text-muted-foreground">
              Inputs changed. Calculate again to view a result for these inputs.
            </p>
          )}
          {unchanged &&
            submitted &&
            (identityError || state.error === changedRevision ? (
              <div role="alert" className="space-y-3 text-sm">
                <p>{identityError ?? changedRevision}</p>
                <Button
                  variant="outline"
                  onClick={() => window.location.reload()}
                >
                  Reload company
                </Button>
              </div>
            ) : state.error === "This record was not found." ? (
              <p role="status" className="rounded-md border p-3 text-sm">
                This analysis is unavailable for the selected model or current
                application version. Accepted valuation and source evidence
                remain available above.
              </p>
            ) : state.data ? (
              <ReturnHurdleResult data={state.data} />
            ) : (
              <PendingOrError error={state.error} retry={state.retry} />
            ))}
        </CardContent>
      )}
    </Card>
  );
}
