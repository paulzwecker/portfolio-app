"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError, useResearch } from "@/components/research-frame";
import {
  isFinancialModel,
  isFinancialModels,
  isFinancialModelRevisionDetail,
  isFinancialModelContract,
  isFinancialModelContractImport,
  isFinancialModelContractPreview,
  isFinancialModelCalculationPreview,
  type DcfOperatingBase,
  type DcfScenario,
  type FinancialModel,
  type FinancialModelContract,
  type FinancialModelContractPreview,
  type FinancialModelCalculationPreview,
  type FinancialModelCreate,
  type FinancialModelRevision,
  type FinancialModelRevisionCreate,
  type FinancialModelOutputs,
} from "@/lib/domain-contracts";
import { date, percent } from "@/lib/display";

type DcfDraft = {
  base: { [Key in keyof DcfOperatingBase]: string };
  scenarios: DraftScenario[];
  rationale: string;
  source: string;
};

type DraftYear = {
  forecast_year: number;
  revenue_growth: string;
  ebit_margin: string;
  tax_rate: string;
  da_to_revenue: string;
  capex_to_revenue: string;
  nwc_to_revenue: string;
  discount_rate: string;
};

type DraftScenario = {
  scenario: DcfScenario;
  probability: string;
  terminal_growth: string;
  year10_ufcf_growth: string;
  rationale: string;
  years: DraftYear[];
};

type ValuationListing = {
  id: string;
  security_id: string;
  ticker: string;
  venue: string;
  currency?: string | null;
  is_demo: boolean;
};

type EditorState = {
  model: FinancialModel | null;
  name: string;
  listingId: string;
  currency: string;
  draft: DcfDraft;
};

type BaseField = keyof DcfOperatingBase;
type YearField = Exclude<keyof DraftYear, "forecast_year">;

const scenarioNames: DcfScenario[] = ["BEAR", "BASE", "BULL"];
const baseFields: Array<[BaseField, string]> = [
  ["base_revenue", "Base revenue (billions)"],
  ["base_ebit_margin", "Base EBIT margin"],
  ["base_tax_rate", "Base tax rate"],
  ["base_da_to_revenue", "Base D&A / revenue"],
  ["base_capex_to_revenue", "Base capex / revenue"],
  ["base_nwc_to_revenue", "Base NWC / revenue"],
  ["net_cash_debt", "Net cash / (debt), billions"],
  ["diluted_shares", "Diluted shares, billions"],
];
const yearFields: Array<[YearField, string]> = [
  ["revenue_growth", "Revenue growth"],
  ["ebit_margin", "EBIT margin"],
  ["tax_rate", "Tax rate"],
  ["da_to_revenue", "D&A / revenue"],
  ["capex_to_revenue", "Capex / revenue"],
  ["nwc_to_revenue", "NWC / revenue"],
  ["discount_rate", "Discount rate"],
];
const modelUnits = "Enter ratios as decimals; for example, 0.12 means 12%.";

function emptyDraft(): DcfDraft {
  return {
    rationale: "",
    source: "",
    base: {
      base_revenue: "",
      base_ebit_margin: "",
      base_tax_rate: "",
      base_da_to_revenue: "",
      base_capex_to_revenue: "",
      base_nwc_to_revenue: "",
      net_cash_debt: "",
      diluted_shares: "",
    },
    scenarios: scenarioNames.map((scenario) => ({
      scenario,
      probability: "",
      terminal_growth: "",
      year10_ufcf_growth: "",
      rationale: "",
      years: Array.from({ length: 5 }, (_, index) => ({
        forecast_year: index + 1,
        revenue_growth: "",
        ebit_margin: "",
        tax_rate: "",
        da_to_revenue: "",
        capex_to_revenue: "",
        nwc_to_revenue: "",
        discount_rate: "",
      })),
    })),
  };
}

function draftFromRevision(revision: FinancialModelRevision): DcfDraft {
  return {
    rationale: "",
    source: "",
    base: {
      base_revenue: revision.base.base_revenue,
      base_ebit_margin: revision.base.base_ebit_margin,
      base_tax_rate: revision.base.base_tax_rate,
      base_da_to_revenue: revision.base.base_da_to_revenue,
      base_capex_to_revenue: revision.base.base_capex_to_revenue,
      base_nwc_to_revenue: revision.base.base_nwc_to_revenue,
      net_cash_debt: revision.base.net_cash_debt,
      diluted_shares: revision.base.diluted_shares,
    },
    scenarios: revision.scenarios.map((scenario) => ({
      scenario: scenario.scenario,
      probability: scenario.probability,
      terminal_growth: scenario.terminal_growth,
      year10_ufcf_growth: scenario.year10_ufcf_growth,
      rationale: scenario.rationale,
      years: scenario.years.map((year) => ({
        forecast_year: year.forecast_year,
        revenue_growth: year.revenue_growth,
        ebit_margin: year.ebit_margin,
        tax_rate: year.tax_rate,
        da_to_revenue: year.da_to_revenue,
        capex_to_revenue: year.capex_to_revenue,
        nwc_to_revenue: year.nwc_to_revenue,
        discount_rate: year.discount_rate,
      })),
    })),
  };
}

function draftHasCalculationInputs(draft: DcfDraft): boolean {
  return (
    Object.values(draft.base).every((value) => value.trim().length > 0) &&
    draft.scenarios.every(
      (scenario) =>
        scenario.rationale.trim().length > 0 &&
        [
          scenario.probability,
          scenario.terminal_growth,
          scenario.year10_ufcf_growth,
          ...scenario.years.flatMap((year) =>
            yearFields.map(([field]) => year[field]),
          ),
        ].every((value) => value.trim().length > 0),
    )
  );
}

type OutputComparable = Pick<
  FinancialModelOutputs,
  | "bear_fv"
  | "base_fv"
  | "bull_fv"
  | "weighted_fv"
  | "weighted_upside"
  | "expected_cash_flow_irr"
  | "hurdle"
  | "expected_excess"
>;

const comparedOutputs: Array<{
  field: keyof OutputComparable;
  label: string;
  ratio?: boolean;
}> = [
  { field: "bear_fv", label: "Bear fair value" },
  { field: "base_fv", label: "Base fair value" },
  { field: "bull_fv", label: "Bull fair value" },
  { field: "weighted_fv", label: "Weighted fair value" },
  { field: "weighted_upside", label: "Weighted upside", ratio: true },
  {
    field: "expected_cash_flow_irr",
    label: "Expected cash-flow IRR",
    ratio: true,
  },
  { field: "hurdle", label: "Hurdle", ratio: true },
  { field: "expected_excess", label: "Expected excess", ratio: true },
];

function OutputComparison({
  previous,
  proposed,
  currency,
}: {
  previous: OutputComparable | null;
  proposed: OutputComparable;
  currency: string;
}) {
  return (
    <dl className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {comparedOutputs.map(({ field, label, ratio }) => {
        const before = previous?.[field] ?? null;
        const after = proposed[field];
        const changed = previous !== null && before !== after;
        return (
          <div key={field} className="min-w-0 rounded-md bg-secondary/40 p-3">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-1 break-words text-xs tabular-nums">
              <span className="text-muted-foreground">
                {previous === null
                  ? "No accepted baseline"
                  : ratio
                    ? percent(before)
                    : amount(before, currency)}
              </span>
              <span className="px-1.5 text-muted-foreground" aria-hidden="true">
                →
              </span>
              <span className="font-semibold">
                {ratio ? percent(after) : amount(after, currency)}
              </span>
            </dd>
            {previous !== null && (
              <p
                className={`mt-1 text-[11px] ${changed ? "text-primary" : "text-muted-foreground"}`}
              >
                {changed ? "Changed" : "Unchanged"}
              </p>
            )}
          </div>
        );
      })}
    </dl>
  );
}

function ProjectionReview({
  model,
  preview,
  scenarioName,
}: {
  model: FinancialModel | null;
  preview: FinancialModelCalculationPreview;
  scenarioName: DcfScenario;
}) {
  const currentScenario = model?.current_revision.scenarios.find(
    (item) => item.scenario === scenarioName,
  );
  const currentRows = model?.current_revision.projections.filter(
    (item) => item.scenario_id === currentScenario?.id,
  );
  const proposedRows = preview.projections
    .filter((item) => item.scenario === scenarioName)
    .sort((left, right) => left.forecast_year - right.forecast_year);
  const priorByYear = new Map(
    (currentRows ?? []).map((projection) => [
      projection.forecast_year,
      projection,
    ]),
  );
  return (
    <div className="max-w-full overflow-x-auto rounded-md border">
      <table className="w-full min-w-[38rem] text-left text-xs">
        <thead className="bg-secondary/50 text-muted-foreground">
          <tr>
            <th className="p-2 font-medium">Year</th>
            <th className="p-2 font-medium">Revenue, bn · prior → draft</th>
            <th className="p-2 font-medium">UFCF, bn · prior → draft</th>
            <th className="p-2 font-medium">PV of UFCF · prior → draft</th>
            <th className="p-2 font-medium">Discount rate</th>
          </tr>
        </thead>
        <tbody>
          {proposedRows.map((row) => {
            const before = priorByYear.get(row.forecast_year);
            const projectionValue = (value: string | null | undefined) =>
              value === undefined
                ? "No prior revision"
                : value === null
                  ? "Not modeled"
                  : number(value);
            return (
              <tr key={row.forecast_year} className="border-t">
                <th className="p-2 font-medium">{row.forecast_year}</th>
                <td className="p-2 tabular-nums">
                  {projectionValue(before?.revenue)} →{" "}
                  {projectionValue(row.revenue)}
                </td>
                <td className="p-2 tabular-nums">
                  {projectionValue(before?.unlevered_free_cash_flow)} →{" "}
                  {projectionValue(row.unlevered_free_cash_flow)}
                </td>
                <td className="p-2 tabular-nums">
                  {projectionValue(before?.present_value_ufcf)} →{" "}
                  {projectionValue(row.present_value_ufcf)}
                </td>
                <td className="p-2 tabular-nums">
                  {percent(row.discount_rate)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RevisionComparison({
  previous,
  current,
  currency,
}: {
  previous: FinancialModelRevision;
  current: FinancialModelRevision;
  currency: string;
}) {
  const inputChanges: Array<{ path: string; before: string; after: string }> =
    [];
  for (const [field, label] of baseFields) {
    const before = previous.base[field];
    const after = current.base[field];
    if (before !== after) inputChanges.push({ path: label, before, after });
  }
  for (const scenarioName of scenarioNames) {
    const beforeScenario = previous.scenarios.find(
      (item) => item.scenario === scenarioName,
    );
    const afterScenario = current.scenarios.find(
      (item) => item.scenario === scenarioName,
    );
    if (!beforeScenario || !afterScenario) continue;
    for (const field of [
      "probability",
      "terminal_growth",
      "year10_ufcf_growth",
    ] as const) {
      if (beforeScenario[field] !== afterScenario[field])
        inputChanges.push({
          path: `${scenarioName} ${field.replaceAll("_", " ")}`,
          before: beforeScenario[field],
          after: afterScenario[field],
        });
    }
    for (const [field, label] of yearFields) {
      const afterYears = new Map(
        afterScenario.years.map((year) => [year.forecast_year, year]),
      );
      for (const year of beforeScenario.years) {
        const after = afterYears.get(year.forecast_year);
        if (after && year[field] !== after[field])
          inputChanges.push({
            path: `${scenarioName} year ${year.forecast_year} ${label}`,
            before: year[field],
            after: after[field],
          });
      }
    }
  }
  return (
    <details className="mt-3 rounded-md border bg-background p-3">
      <summary className="cursor-pointer text-xs font-medium">
        Compare with current revision · {inputChanges.length} changed assumption
        {inputChanges.length === 1 ? "" : "s"}
      </summary>
      <div className="mt-3 space-y-4">
        {inputChanges.length > 0 ? (
          <ul className="max-h-56 space-y-1 overflow-auto text-xs">
            {inputChanges.map((change) => (
              <li key={change.path} className="break-words">
                <span className="font-medium">{change.path}</span>:{" "}
                {change.before} → {change.after}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">
            No operating-assumption differences.
          </p>
        )}
        <div>
          <p className="mb-2 text-xs font-medium">Normalized outputs</p>
          <OutputComparison
            previous={previous.outputs}
            proposed={current.outputs}
            currency={currency}
          />
        </div>
      </div>
    </details>
  );
}

function amount(value: string | null, currency: string, digits = 2) {
  if (value === null) return "Not supplied";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function number(value: string | null, digits = 2) {
  if (value === null) return "Not supplied";
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function DecimalField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block min-w-0 space-y-1.5 text-xs">
      <span className="font-medium">{label}</span>
      <input
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-10 w-full rounded-md border bg-background px-3 py-2 text-sm tabular-nums"
      />
    </label>
  );
}

function ReadBase({ base }: { base: FinancialModelRevision["base"] }) {
  const labels: Array<[BaseField, string, boolean]> = [
    ["base_revenue", "Base revenue", false],
    ["base_ebit_margin", "EBIT margin", true],
    ["base_tax_rate", "Tax rate", true],
    ["base_da_to_revenue", "D&A / revenue", true],
    ["base_capex_to_revenue", "Capex / revenue", true],
    ["base_nwc_to_revenue", "NWC / revenue", true],
    ["net_cash_debt", "Net cash / (debt)", false],
    ["diluted_shares", "Diluted shares", false],
  ];
  return (
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {labels.map(([field, label, isRatio]) => (
        <div key={field} className="min-w-0 rounded-md bg-secondary/50 p-3">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="mt-1 break-words text-sm font-medium tabular-nums">
            {isRatio ? percent(base[field]) : number(base[field])}
            {field === "base_revenue" ||
            field === "net_cash_debt" ||
            field === "diluted_shares"
              ? " bn"
              : ""}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function RevisionInspection({
  revision,
}: {
  revision: FinancialModelRevision;
}) {
  return (
    <div className="space-y-4">
      <ReadBase base={revision.base} />
      <div className="grid gap-3 xl:grid-cols-3">
        {revision.scenarios.map((scenario) => {
          const projections = revision.projections.filter(
            (item) => item.scenario_id === scenario.id,
          );
          const fairValue =
            scenario.scenario === "BEAR"
              ? revision.outputs.bear_fv
              : scenario.scenario === "BASE"
                ? revision.outputs.base_fv
                : revision.outputs.bull_fv;
          return (
            <details
              key={scenario.id}
              className="min-w-0 rounded-lg border p-3 open:bg-card"
            >
              <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 text-sm font-medium">
                <span>{scenario.scenario} case</span>
                <span className="text-xs text-muted-foreground">
                  {percent(scenario.probability)} probability ·{" "}
                  {amount(fairValue, revision.outputs.model_currency)} / share
                </span>
              </summary>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {scenario.rationale}
              </p>
              <div className="mt-3 space-y-2">
                {projections.map((projection) => (
                  <div
                    key={projection.id}
                    className="rounded-md bg-secondary/40 p-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-medium">
                      <span>Year {projection.forecast_year}</span>
                      {projection.forecast_year > 5 && (
                        <span className="text-muted-foreground">
                          UFCF-only fade; detailed lines not modeled
                        </span>
                      )}
                    </div>
                    <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-xs sm:grid-cols-3">
                      {projection.revenue !== null && (
                        <div>
                          <dt className="text-muted-foreground">Revenue, bn</dt>
                          <dd className="mt-0.5 tabular-nums">
                            {number(projection.revenue)}
                          </dd>
                        </div>
                      )}
                      {projection.ebit !== null && (
                        <div>
                          <dt className="text-muted-foreground">EBIT, bn</dt>
                          <dd className="mt-0.5 tabular-nums">
                            {number(projection.ebit)}
                          </dd>
                        </div>
                      )}
                      <div>
                        <dt className="text-muted-foreground">UFCF, bn</dt>
                        <dd className="mt-0.5 tabular-nums">
                          {number(projection.unlevered_free_cash_flow)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">UFCF growth</dt>
                        <dd className="mt-0.5 tabular-nums">
                          {percent(projection.revenue_growth)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Discount rate</dt>
                        <dd className="mt-0.5 tabular-nums">
                          {percent(projection.discount_rate)}
                        </dd>
                      </div>
                      {projection.terminal_value !== null && (
                        <div>
                          <dt className="text-muted-foreground">
                            Terminal value, bn
                          </dt>
                          <dd className="mt-0.5 tabular-nums">
                            {number(projection.terminal_value)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </div>
                ))}
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
}

function ScenarioEditor({
  scenario,
  onChange,
}: {
  scenario: DraftScenario;
  onChange: (next: DraftScenario) => void;
}) {
  return (
    <details className="rounded-lg border p-4">
      <summary className="cursor-pointer text-sm font-semibold">
        {scenario.scenario} scenario · 5-year operating assumptions
      </summary>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <DecimalField
          label="Scenario probability"
          value={scenario.probability}
          onChange={(probability) => onChange({ ...scenario, probability })}
        />
        <DecimalField
          label="Terminal growth"
          value={scenario.terminal_growth}
          onChange={(terminal_growth) =>
            onChange({ ...scenario, terminal_growth })
          }
        />
        <DecimalField
          label="Year 10 UFCF growth target"
          value={scenario.year10_ufcf_growth}
          onChange={(year10_ufcf_growth) =>
            onChange({ ...scenario, year10_ufcf_growth })
          }
        />
      </div>
      <label className="mt-3 block space-y-1.5 text-xs">
        <span className="font-medium">Scenario rationale</span>
        <textarea
          required
          minLength={1}
          value={scenario.rationale}
          onChange={(event) =>
            onChange({ ...scenario, rationale: event.target.value })
          }
          rows={2}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
      </label>
      <div className="mt-4 space-y-2">
        {scenario.years.map((year, index) => (
          <details
            key={year.forecast_year}
            className="rounded-md bg-secondary/40 p-3"
          >
            <summary className="cursor-pointer text-xs font-medium">
              Year {year.forecast_year}
            </summary>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {yearFields.map(([field, label]) => (
                <DecimalField
                  key={field}
                  label={label}
                  value={year[field]}
                  onChange={(value) => {
                    const years = [...scenario.years];
                    years[index] = { ...year, [field]: value };
                    onChange({ ...scenario, years });
                  }}
                />
              ))}
            </div>
          </details>
        ))}
      </div>
    </details>
  );
}

function ModelEditor({
  companyId,
  editor,
  listings,
  busy,
  error,
  cancel,
  reload,
  save,
  onChange,
}: {
  companyId: string;
  editor: EditorState;
  listings: ValuationListing[];
  busy: boolean;
  error: string | null;
  cancel: () => void;
  reload: () => void;
  save: (event: React.FormEvent<HTMLFormElement>) => void;
  onChange: (next: EditorState) => void;
}) {
  const calculationRequest = editor.model
    ? {
        base_revision_id: editor.model.current_revision_id,
        base: editor.draft.base,
        scenarios: editor.draft.scenarios,
      }
    : {
        valuation_listing_id: editor.listingId,
        model_currency: editor.currency,
        base: editor.draft.base,
        scenarios: editor.draft.scenarios,
      };
  const requestKey = JSON.stringify(calculationRequest);
  const previewPath = editor.model
    ? `financial-models/${editor.model.id}/revisions/preview`
    : `companies/${encodeURIComponent(companyId)}/financial-models/preview`;
  const inputsComplete =
    draftHasCalculationInputs(editor.draft) &&
    (editor.model !== null ||
      (editor.listingId.length > 0 && /^[A-Z]{3}$/.test(editor.currency)));
  const [previewState, setPreviewState] = useState<{
    key: string;
    data: FinancialModelCalculationPreview;
  } | null>(null);
  const [previewIssue, setPreviewIssue] = useState<{
    key: string;
    message: string;
  } | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<DcfScenario>("BASE");
  const activePreview =
    previewState?.key === requestKey ? previewState.data : null;
  const previewError =
    previewIssue?.key === requestKey ? previewIssue.message : null;
  const previewBusy =
    inputsComplete && activePreview === null && previewError === null;

  useEffect(() => {
    if (!inputsComplete) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/research/${previewPath}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: requestKey,
          signal: controller.signal,
        });
        const result: unknown = await response.json();
        if (!response.ok) {
          setPreviewIssue({
            key: requestKey,
            message:
              typeof result === "object" &&
              result !== null &&
              "detail" in result
                ? String(result.detail)
                : "The draft could not be recalculated.",
          });
        } else if (!isFinancialModelCalculationPreview(result)) {
          setPreviewIssue({
            key: requestKey,
            message:
              "The calculation response failed contract validation. Reload before accepting.",
          });
        } else {
          setPreviewState({ key: requestKey, data: result });
        }
      } catch {
        if (!controller.signal.aborted)
          setPreviewIssue({
            key: requestKey,
            message:
              "Research services are unavailable. The accepted model remains unchanged.",
          });
      }
    }, 400);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [inputsComplete, previewPath, requestKey]);

  const updateBase = (field: BaseField, value: string) =>
    onChange({
      ...editor,
      draft: {
        ...editor.draft,
        base: { ...editor.draft.base, [field]: value },
      },
    });
  const updateScenario = (index: number, next: DraftScenario) => {
    const scenarios = [...editor.draft.scenarios];
    scenarios[index] = next;
    onChange({ ...editor, draft: { ...editor.draft, scenarios } });
  };
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    if (!activePreview || previewBusy || busy) {
      event.preventDefault();
      return;
    }
    save(event);
  };
  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-5 rounded-xl border bg-card p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">
            {editor.model
              ? "Append a DCF revision"
              : "Create the first DCF model"}
          </h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            Edit the supported assumptions and inspect the API calculation
            before accepting. A successful accept appends an immutable revision.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={cancel}>
          Cancel
        </Button>
      </div>
      {!editor.model && (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block space-y-1.5 text-xs">
            <span className="font-medium">Model name</span>
            <input
              required
              value={editor.name}
              onChange={(event) =>
                onChange({ ...editor, name: event.target.value })
              }
              className="min-h-10 w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
          </label>
          <label className="block space-y-1.5 text-xs">
            <span className="font-medium">Valuation listing</span>
            <select
              required
              value={editor.listingId}
              onChange={(event) =>
                onChange({ ...editor, listingId: event.target.value })
              }
              className="min-h-10 w-full rounded-md border bg-background px-3 py-2 text-sm"
            >
              <option value="">Select listing</option>
              {listings.map((listing) => (
                <option key={listing.id} value={listing.id}>
                  {listing.ticker} · {listing.venue} ·{" "}
                  {listing.currency ?? "currency unknown"}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1.5 text-xs sm:col-span-2">
            <span className="font-medium">Model currency</span>
            <input
              required
              minLength={3}
              maxLength={3}
              pattern="[A-Z]{3}"
              value={editor.currency}
              onChange={(event) =>
                onChange({
                  ...editor,
                  currency: event.target.value.toUpperCase(),
                })
              }
              placeholder="Select an explicit ISO currency, for example USD"
              className="min-h-10 w-full rounded-md border bg-background px-3 py-2 text-sm sm:max-w-xs"
            />
          </label>
        </div>
      )}
      {editor.model && (
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="outline">
            {editor.model.model_name} · {editor.model.model_currency}
          </Badge>
          <Badge variant="outline">
            {editor.model.valuation_listing.ticker} ·{" "}
            {editor.model.valuation_listing.venue}
          </Badge>
          <Badge variant="outline">
            Based on revision {editor.model.current_revision.revision_number}
          </Badge>
        </div>
      )}
      <section className="space-y-3">
        <div>
          <h4 className="text-sm font-medium">
            Base-year and valuation inputs
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Revenue and shares are in billions, following the reference model
            units. {modelUnits}
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {baseFields.map(([field, label]) => (
            <DecimalField
              key={field}
              label={label}
              value={editor.draft.base[field]}
              onChange={(value) => updateBase(field, value)}
            />
          ))}
        </div>
      </section>
      <section className="space-y-3">
        <div>
          <h4 className="text-sm font-medium">Bear, Base and Bull scenarios</h4>
          <p className="mt-1 text-xs text-muted-foreground">
            Probabilities must sum exactly to 1. Years 6–10 fade UFCF growth;
            detailed operating lines are intentionally not editable beyond Year
            5.
          </p>
        </div>
        <div className="space-y-3">
          {editor.draft.scenarios.map((scenario, index) => (
            <ScenarioEditor
              key={scenario.scenario}
              scenario={scenario}
              onChange={(next) => updateScenario(index, next)}
            />
          ))}
        </div>
      </section>
      <section
        aria-label="Draft calculation preview"
        className="space-y-4 rounded-lg border bg-background p-3 sm:p-4"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold">Draft calculation</h4>
            <p className="mt-1 text-xs text-muted-foreground">
              Deterministic UFCF DCF preview from the canonical API. Previewing
              does not create or update a revision.
            </p>
          </div>
          {activePreview && (
            <Badge
              variant={
                activePreview.outputs.status === "COMPLETE"
                  ? "outline"
                  : "secondary"
              }
            >
              {activePreview.outputs.status} · price{" "}
              {activePreview.outputs.price_status.replaceAll("_", " ")}
            </Badge>
          )}
        </div>
        {!inputsComplete && (
          <p className="text-xs text-muted-foreground">
            Complete every base, scenario and Year 1–5 assumption, then enter a
            rationale for each scenario to calculate this draft.
          </p>
        )}
        {previewBusy && (
          <p role="status" className="text-xs text-muted-foreground">
            Recalculating projections and normalized outputs…
          </p>
        )}
        {previewError && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-destructive/40 p-3">
            <p role="alert" className="text-xs text-destructive">
              {previewError}
            </p>
            {editor.model && /changed|conflict/i.test(previewError) && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={reload}
              >
                Reload current revision
              </Button>
            )}
          </div>
        )}
        {activePreview && (
          <>
            <div>
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h5 className="text-xs font-semibold">
                  Normalized output consequences
                </h5>
                <span className="text-[11px] text-muted-foreground">
                  {editor.model
                    ? `Accepted revision ${editor.model.current_revision.revision_number} → draft`
                    : "First revision · no accepted baseline"}
                </span>
              </div>
              <OutputComparison
                previous={editor.model?.current_revision.outputs ?? null}
                proposed={activePreview.outputs}
                currency={activePreview.model_currency}
              />
              {(activePreview.outputs.price_unavailable_reason ||
                activePreview.outputs.irr_unavailable_reason) && (
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  {activePreview.outputs.price_unavailable_reason ??
                    activePreview.outputs.irr_unavailable_reason}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h5 className="text-xs font-semibold">
                    Ten-year projections
                  </h5>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Years 6–10 contain UFCF growth only in this methodology.
                  </p>
                </div>
                <div
                  className="flex gap-1"
                  role="group"
                  aria-label="Projection scenario"
                >
                  {scenarioNames.map((scenario) => (
                    <Button
                      key={scenario}
                      type="button"
                      size="sm"
                      variant={
                        selectedScenario === scenario ? "secondary" : "ghost"
                      }
                      aria-pressed={selectedScenario === scenario}
                      onClick={() => setSelectedScenario(scenario)}
                    >
                      {scenario}
                    </Button>
                  ))}
                </div>
              </div>
              <ProjectionReview
                model={editor.model}
                preview={activePreview}
                scenarioName={selectedScenario}
              />
            </div>
          </>
        )}
      </section>
      <label className="block space-y-1.5 text-xs">
        <span className="font-medium">Source URL or reference (optional)</span>
        <input
          value={editor.draft.source}
          onChange={(event) =>
            onChange({
              ...editor,
              draft: { ...editor.draft, source: event.target.value },
            })
          }
          maxLength={1000}
          placeholder="Filing, transcript, research note or source URL"
          className="min-h-10 w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
      </label>
      <label className="block space-y-1.5 text-xs">
        <span className="font-medium">Revision rationale</span>
        <textarea
          required
          minLength={1}
          maxLength={4000}
          value={editor.draft.rationale}
          onChange={(event) =>
            onChange({
              ...editor,
              draft: { ...editor.draft, rationale: event.target.value },
            })
          }
          rows={3}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
      </label>
      {error && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-destructive/40 p-3">
          <p role="alert" className="text-sm">
            {error}
          </p>
          {editor.model && /changed|conflict/i.test(error) && (
            <Button type="button" variant="outline" size="sm" onClick={reload}>
              Reload current revision
            </Button>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={busy || !activePreview || previewBusy}>
          {busy
            ? "Accepting revision…"
            : editor.model
              ? "Accept model revision"
              : "Create model with revision 1"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Acceptance rechecks the base revision and recalculates atomically.
        </p>
      </div>
    </form>
  );
}

export function CanonicalDcfExplorer({
  companyId,
  listings,
}: {
  companyId: string;
  listings: ValuationListing[];
}) {
  const state = useResearch(
    `companies/${encodeURIComponent(companyId)}/financial-models`,
    isFinancialModels,
  );
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inspected, setInspected] = useState<
    Record<string, FinancialModelRevision | undefined>
  >({});
  const models = state.data ?? [];

  const beginCreate = () => {
    setNotice(null);
    setError(null);
    setEditor({
      model: null,
      name: "Operating UFCF DCF",
      listingId: "",
      currency: "",
      draft: emptyDraft(),
    });
  };
  const beginRevision = (model: FinancialModel) => {
    setNotice(null);
    setError(null);
    setEditor({
      model,
      name: model.model_name,
      listingId: model.valuation_listing.id,
      currency: model.model_currency,
      draft: draftFromRevision(model.current_revision),
    });
  };
  const cancelEditor = () => {
    setEditor(null);
    setError(null);
  };

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editor) return;
    setBusy(true);
    setError(null);
    const revision: FinancialModelRevisionCreate = {
      base_revision_id: editor.model?.current_revision_id ?? null,
      source_revision_id: null,
      actor: "LOCAL_USER",
      source: editor.draft.source.trim() || "Company Explorer",
      rationale: editor.draft.rationale,
      effective_at: new Date().toISOString(),
      base: editor.draft.base,
      scenarios: editor.draft.scenarios,
    };
    const path = editor.model
      ? `financial-models/${editor.model.id}/revisions`
      : `companies/${encodeURIComponent(companyId)}/financial-models`;
    const body: FinancialModelCreate | FinancialModelRevisionCreate =
      editor.model
        ? revision
        : {
            model_type: "UFCF_DCF_10Y_FADE",
            model_name: editor.name,
            valuation_listing_id: editor.listingId,
            model_currency: editor.currency,
            source_model_key: null,
            initial_revision: revision,
          };
    try {
      const response = await fetch(`/api/research/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result: unknown = await response.json();
      if (!response.ok) {
        setError(
          typeof result === "object" && result !== null && "detail" in result
            ? String(result.detail)
            : "The model revision could not be accepted.",
        );
      } else if (
        editor.model
          ? !isFinancialModelRevisionDetail(result)
          : !isFinancialModel(result)
      ) {
        setError(
          "The accepted model response failed contract validation. Reload before retrying.",
        );
      } else {
        const number = editor.model
          ? (result as FinancialModelRevision).revision_number
          : (result as FinancialModel).current_revision.revision_number;
        setEditor(null);
        setNotice(
          editor.model
            ? `Revision ${number} accepted. ${comparedOutputs.filter(({ field }) => editor.model!.current_revision.outputs[field] !== (result as FinancialModelRevision).outputs[field]).length} normalized outputs changed; the prior revision remains in history.`
            : `First model revision ${number} accepted with its calculated outputs and projections.`,
        );
        state.retry();
      }
    } catch {
      setError(
        "Research services are unavailable. Retry after checking the API and database.",
      );
    } finally {
      setBusy(false);
    }
  };

  const inspectRevision = async (modelId: string, revisionId: string) => {
    if (inspected[revisionId]) return;
    try {
      const response = await fetch(
        `/api/research/financial-models/${modelId}/revisions/${revisionId}`,
        { cache: "no-store" },
      );
      const result: unknown = await response.json();
      if (response.ok && isFinancialModelRevisionDetail(result))
        setInspected((current) => ({ ...current, [revisionId]: result }));
    } catch {
      // The summary remains available if the detailed historical read is offline.
    }
  };

  return (
    <section
      id="canonical-models"
      aria-labelledby="canonical-models-title"
      className="mb-8 scroll-mt-5 space-y-4"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="canonical-models-title" className="text-xl font-semibold">
            Canonical financial models
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
            Native 10-year UFCF DCF state is versioned and recalculated by the
            API. Imported workbook output snapshots remain separate reference
            history below.
          </p>
        </div>
        {state.data && !editor && (
          <Button variant="outline" onClick={beginCreate}>
            {models.length === 0 ? "Create first DCF model" : "Add DCF model"}
          </Button>
        )}
      </div>

      {!state.data && (
        <PendingOrError error={state.error} retry={state.retry} />
      )}
      {notice && (
        <p
          role="status"
          className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm"
        >
          {notice}
        </p>
      )}
      {state.data && models.length === 0 && !editor && (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          No application-owned financial model has been accepted. Imported
          outputs below remain historical source snapshots and are not editable
          assumptions.
        </p>
      )}

      {models.map((model) => {
        const output = model.current_revision.outputs;
        return (
          <Card key={model.id} className="min-w-0 shadow-none">
            <CardHeader className="gap-3 pb-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base">
                    {model.model_name}
                  </CardTitle>
                  <Badge
                    variant={
                      output.status === "COMPLETE" ? "default" : "secondary"
                    }
                  >
                    {output.status}
                  </Badge>
                  <Badge variant="outline">
                    {model.model_type.replaceAll("_", " ")}
                  </Badge>
                </div>
                <p className="mt-1 break-words text-xs text-muted-foreground">
                  {model.valuation_listing.ticker} ·{" "}
                  {model.valuation_listing.venue} · {model.model_currency} ·
                  revision {model.current_revision.revision_number}
                  {model.source_model_key &&
                    ` · source ${model.source_model_key}`}
                </p>
              </div>
              {!editor && (
                <Button variant="outline" onClick={() => beginRevision(model)}>
                  Revise assumptions
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <OutputValue
                  label="Bear fair value / share"
                  value={output.bear_fv}
                  currency={model.model_currency}
                />
                <OutputValue
                  label="Base fair value / share"
                  value={output.base_fv}
                  currency={model.model_currency}
                />
                <OutputValue
                  label="Bull fair value / share"
                  value={output.bull_fv}
                  currency={model.model_currency}
                />
                <OutputValue
                  label="Weighted fair value / share"
                  value={output.weighted_fv}
                  currency={model.model_currency}
                />
                <OutputValue
                  label="Weighted upside"
                  value={output.weighted_upside}
                  ratio
                />
                <OutputValue
                  label="Expected cash-flow IRR"
                  value={output.expected_cash_flow_irr}
                  ratio
                />
                <OutputValue label="Hurdle" value={output.hurdle} ratio />
                <OutputValue
                  label="Expected excess"
                  value={output.expected_excess}
                  ratio
                />
              </div>
              <div className="flex flex-wrap items-center gap-2 border-t pt-3 text-xs">
                <Badge
                  variant={
                    output.price_status === "FRESH" ? "outline" : "secondary"
                  }
                >
                  Price {output.price_status.replaceAll("_", " ")}
                </Badge>
                <span className="text-muted-foreground">
                  Current quote:{" "}
                  {output.current_price === null
                    ? "Not available"
                    : `${amount(output.current_price, output.model_currency)} · ${output.price_effective_at ? date(output.price_effective_at) : "date not supplied"}`}
                </span>
                <span className="text-muted-foreground">
                  Forward Fundamental CAGR:{" "}
                  {output.forward_fundamental_cagr === null
                    ? "not produced by this DCF type"
                    : percent(output.forward_fundamental_cagr)}
                </span>
              </div>
              {(output.price_unavailable_reason ||
                output.irr_unavailable_reason) && (
                <p className="text-xs leading-5 text-muted-foreground">
                  {output.price_unavailable_reason ??
                    output.irr_unavailable_reason}
                </p>
              )}
              <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                <p>
                  Accepted {date(model.current_revision.recorded_at)} ·
                  effective {date(model.current_revision.effective_at)} ·{" "}
                  {model.current_revision.actor}
                </p>
                <p className="break-words">
                  {model.current_revision.source ?? "Source not recorded"} ·{" "}
                  {model.current_revision.rationale}
                </p>
              </div>
              <ModelContractSync
                modelId={model.id}
                ticker={model.valuation_listing.ticker}
                onImported={() => {
                  setNotice(
                    "External model revision accepted and added to history.",
                  );
                  state.retry();
                }}
              />
              <details className="rounded-lg border p-4">
                <summary className="cursor-pointer text-sm font-medium">
                  Accepted assumptions and derived projections
                </summary>
                <div className="mt-4 space-y-4">
                  <ReadBase base={model.current_revision.base} />
                  <RevisionInspection revision={model.current_revision} />
                </div>
              </details>
              <details className="rounded-lg border p-4">
                <summary className="cursor-pointer text-sm font-medium">
                  Revision history ({model.history.length})
                </summary>
                {model.history.filter(
                  (revision) => revision.id !== model.current_revision_id,
                ).length === 0 ? (
                  <p className="mt-3 text-xs text-muted-foreground">
                    This is the first accepted revision.
                  </p>
                ) : (
                  <ul className="mt-3 space-y-3">
                    {model.history
                      .filter(
                        (revision) => revision.id !== model.current_revision_id,
                      )
                      .map((revision) => (
                        <li
                          key={revision.id}
                          className="rounded-md bg-secondary/40 p-3"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-medium">
                              Revision {revision.revision_number}
                            </p>
                            <Badge variant="outline">
                              {revision.actor} · {revision.outputs.status}
                            </Badge>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            Effective {date(revision.effective_at)} · recorded{" "}
                            {date(revision.recorded_at)} ·{" "}
                            {revision.source ?? "source not recorded"}
                          </p>
                          <p className="mt-2 break-words text-xs">
                            {revision.rationale}
                          </p>
                          <div className="mt-2 grid gap-2 text-xs sm:grid-cols-3">
                            <span>
                              Weighted FV ·{" "}
                              {amount(
                                revision.outputs.weighted_fv,
                                model.model_currency,
                              )}
                            </span>
                            <span>
                              Expected IRR ·{" "}
                              {percent(revision.outputs.expected_cash_flow_irr)}
                            </span>
                            <span>
                              Data state ·{" "}
                              {revision.outputs.price_status.replaceAll(
                                "_",
                                " ",
                              )}
                            </span>
                          </div>
                          {!inspected[revision.id] ? (
                            <Button
                              type="button"
                              variant="link"
                              className="mt-2 h-auto px-0 text-xs"
                              onClick={() =>
                                void inspectRevision(model.id, revision.id)
                              }
                            >
                              Inspect and compare with current revision
                            </Button>
                          ) : (
                            <div className="mt-3 border-t pt-3">
                              <RevisionInspection
                                revision={inspected[revision.id]!}
                              />
                              <RevisionComparison
                                previous={inspected[revision.id]!}
                                current={model.current_revision}
                                currency={model.model_currency}
                              />
                            </div>
                          )}
                        </li>
                      ))}
                  </ul>
                )}
              </details>
            </CardContent>
          </Card>
        );
      })}

      {editor && (
        <ModelEditor
          companyId={companyId}
          editor={editor}
          listings={listings}
          busy={busy}
          error={error}
          cancel={cancelEditor}
          reload={() => {
            setEditor(null);
            state.retry();
          }}
          save={(event) => void save(event)}
          onChange={setEditor}
        />
      )}
    </section>
  );
}

function ModelContractSync({
  modelId,
  ticker,
  onImported,
}: {
  modelId: string;
  ticker: string;
  onImported: () => void;
}) {
  const [contract, setContract] = useState<FinancialModelContract | null>(null);
  const [preview, setPreview] = useState<FinancialModelContractPreview | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const exportContract = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `/api/research/financial-models/${modelId}/contract`,
        { cache: "no-store" },
      );
      const data: unknown = await response.json();
      if (!response.ok || !isFinancialModelContract(data))
        throw new Error("The portable contract could not be verified.");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${ticker.toLowerCase()}-model-contract-v1.json`;
      link.click();
      URL.revokeObjectURL(url);
      setNotice(
        "Contract exported. Use the Google Sheets adapter, then upload its edited JSON for review.",
      );
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The model contract could not be exported.",
      );
    } finally {
      setBusy(false);
    }
  };

  const previewFile = async (file: File | undefined) => {
    setError(null);
    setNotice(null);
    setContract(null);
    setPreview(null);
    if (!file) return;
    setBusy(true);
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!isFinancialModelContract(parsed))
        throw new Error("This file is not a valid version 1 model contract.");
      if (parsed.model.model_id !== modelId)
        throw new Error("This contract belongs to a different model.");
      const response = await fetch(
        `/api/research/financial-models/${modelId}/contract/preview`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed),
        },
      );
      const data: unknown = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data === "object" && data !== null && "detail" in data
            ? String(data.detail)
            : "The external revision could not be previewed.",
        );
      if (!isFinancialModelContractPreview(data))
        throw new Error("The preview response failed contract validation.");
      setContract(parsed);
      setPreview(data);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The selected contract could not be read.",
      );
    } finally {
      setBusy(false);
    }
  };

  const importContract = async () => {
    if (!contract || preview?.status !== "READY") return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/research/financial-models/${modelId}/contract/import`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(contract),
        },
      );
      const data: unknown = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data === "object" && data !== null && "detail" in data
            ? String(data.detail)
            : "The external revision could not be accepted.",
        );
      if (!isFinancialModelContractImport(data))
        throw new Error("The accepted revision response failed validation.");
      setContract(null);
      setPreview(null);
      onImported();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The external revision could not be accepted.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-label="External model editing"
      className="space-y-3 rounded-lg border bg-secondary/15 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Google Sheets round trip</h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
            Export the versioned JSON contract, edit assumptions in the Sheets
            adapter, then preview the uploaded contract. Acceptance creates a
            new application revision.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => void exportContract()}
        >
          Export contract
        </Button>
      </div>
      <label className="flex flex-col gap-1 text-xs font-medium sm:max-w-sm">
        Preview edited contract
        <input
          type="file"
          accept=".json,application/json"
          disabled={busy}
          onChange={(event) => void previewFile(event.currentTarget.files?.[0])}
          className="block w-full rounded-md border bg-background px-3 py-2 text-xs file:mr-3 file:rounded file:border-0 file:bg-secondary file:px-2 file:py-1 file:text-xs"
        />
      </label>
      {busy && (
        <p role="status" className="text-xs text-muted-foreground">
          Checking portable model state…
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-xs text-muted-foreground">
          {notice}
        </p>
      )}
      {preview && (
        <div className="space-y-3 border-t pt-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">
                Preview: {preview.status.replaceAll("_", " ")}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {preview.reason ??
                  `Based on revision ${contract?.base_revision.revision_number}; current revision ${preview.current_revision_number}.`}
              </p>
              <p className="mt-1 break-all text-xs text-muted-foreground">
                {preview.actor} · {preview.source ?? "source not supplied"} ·
                external id {preview.source_revision_id} · effective{" "}
                {date(preview.effective_at)}
              </p>
            </div>
            {preview.status === "READY" && (
              <Button
                type="button"
                size="sm"
                disabled={busy}
                onClick={() => void importContract()}
              >
                Accept as revision {preview.proposed_revision_number}
              </Button>
            )}
          </div>
          {preview.changes.length > 0 ? (
            <details open className="rounded-md border bg-background p-3">
              <summary className="cursor-pointer text-xs font-medium">
                Assumption and rationale changes ({preview.changes.length})
              </summary>
              <ul className="mt-2 max-h-64 space-y-2 overflow-auto text-xs">
                {preview.changes.map((change) => (
                  <li key={change.path} className="grid gap-1 sm:grid-cols-3">
                    <span className="break-all font-medium">{change.path}</span>
                    <span className="break-all text-muted-foreground">
                      Was: {change.previous ?? "not set"}
                    </span>
                    <span className="break-all">
                      Now: {change.proposed ?? "not set"}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : (
            <p className="text-xs text-muted-foreground">
              No candidate input or rationale changes.
            </p>
          )}
          {preview.output_changes.length > 0 && (
            <details className="rounded-md border bg-background p-3">
              <summary className="cursor-pointer text-xs font-medium">
                Server recalculation differences (
                {preview.output_changes.length})
              </summary>
              <ul className="mt-2 max-h-48 space-y-1 overflow-auto text-xs">
                {preview.output_changes.map((change) => (
                  <li key={change.path} className="break-words">
                    <span className="font-medium">{change.path}</span>:{" "}
                    {change.previous ?? "unavailable"} →{" "}
                    {change.proposed ?? "unavailable"}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}

function OutputValue({
  label,
  value,
  currency,
  ratio,
}: {
  label: string;
  value: string | null;
  currency?: string;
  ratio?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-md bg-secondary/40 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold tabular-nums">
        {ratio ? percent(value) : amount(value, currency ?? "USD")}
      </p>
    </div>
  );
}
