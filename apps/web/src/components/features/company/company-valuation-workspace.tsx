"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, PendingOrError } from "@/components/app/empty-state";
import { MetricCard } from "@/components/app/metric-card";
import { PageSection } from "@/components/app/page-section";
import { StatusIndicator } from "@/components/app/status-indicator";
import { CanonicalArchetypeExplorer } from "@/components/canonical-archetypes";
import { CanonicalDcfExplorer } from "@/components/canonical-dcf";
import { ModelMigrationStatus } from "@/components/model-migration-status";
import { ModelOutputs as CompanyModelOutputHistory } from "@/components/features/company/company-model-output-history";
import { useResearch } from "@/hooks/use-research";
import {
  isCompanyExpectedReturnHistory,
  isCompanyModelOutputsCurrent,
  isExtendedFinancialModels,
  isFinancialModels,
  isRecord,
  type CompanyModelOutputsCurrent,
  type ExtendedFinancialModel,
  type FinancialModel,
  type ReturnMethodology,
} from "@/lib/domain-contracts";
import {
  dateTime,
  formatCurrency,
  formatPercent,
  quantity,
  statusLabel,
} from "@/lib/display";

type Listing = {
  id: string;
  security_id: string;
  ticker: string;
  venue: string;
  currency?: string | null;
  is_demo: boolean;
};

type ModelMethod =
  "UFCF_DCF_10Y_FADE" | "OWNER_CASH_FLOW_10Y" | "RESIDUAL_INCOME_10Y_FADE";

type OutputView = {
  status: string | null;
  modelCurrency: string | null;
  bearFv: string | null;
  baseFv: string | null;
  bullFv: string | null;
  bearProbability: string | null;
  baseProbability: string | null;
  bullProbability: string | null;
  weightedFv: string | null;
  weightedUpside: string | null;
  expectedIrr: string | null;
  hurdle: string | null;
  expectedExcess: string | null;
  forwardCagr: string | null;
  currentPrice: string | null;
  priceStatus: string | null;
  priceEffectiveAt: string | null;
  priceReason: string | null;
  irrReason: string | null;
  methodology: ReturnMethodology | null;
};

type Driver = {
  label: string;
  value: string | null;
  kind?: "ratio" | "amount";
};

type ModelDescriptor = {
  key: string;
  native: boolean;
  method: ModelMethod | null;
  name: string;
  modelId: string | null;
  ticker: string | null;
  venue: string | null;
  listingCurrency: string | null;
  currency: string | null;
  revisionNumber: number | null;
  effectiveAt: string | null;
  recordedAt: string | null;
  actor: string | null;
  source: string | null;
  rationale: string | null;
  output: OutputView | null;
  driverSets: Record<ScenarioName, Driver[]>;
};

const methodLabels: Record<ModelMethod, string> = {
  UFCF_DCF_10Y_FADE: "UFCF DCF",
  OWNER_CASH_FLOW_10Y: "Owner cash flow",
  RESIDUAL_INCOME_10Y_FADE: "Residual income",
};

const methodDescriptions: Record<ModelMethod, string> = {
  UFCF_DCF_10Y_FADE: "Enterprise UFCF with a ten-year fade",
  OWNER_CASH_FLOW_10Y: "Shareholder owner-cash-flow model",
  RESIDUAL_INCOME_10Y_FADE: "Equity residual-income model",
};

const methodOrder: ModelMethod[] = [
  "UFCF_DCF_10Y_FADE",
  "OWNER_CASH_FLOW_10Y",
  "RESIDUAL_INCOME_10Y_FADE",
];

const scenarioNames = ["BEAR", "BASE", "BULL"] as const;
type ScenarioName = (typeof scenarioNames)[number];

function readString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function readNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }
  return null;
}

function readArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => isRecord(item))
    : [];
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function outputView(value: unknown): OutputView | null {
  const item = readRecord(value);
  if (!item) return null;
  const method = readRecord(item.return_methodology);
  return {
    status: readString(item.status),
    modelCurrency: readString(item.model_currency),
    bearFv: readString(item.bear_fv),
    baseFv: readString(item.base_fv),
    bullFv: readString(item.bull_fv),
    bearProbability: readString(item.bear_probability),
    baseProbability: readString(item.base_probability),
    bullProbability: readString(item.bull_probability),
    weightedFv: readString(item.weighted_fv),
    weightedUpside: readString(item.weighted_upside),
    expectedIrr: readString(item.expected_cash_flow_irr),
    hurdle: readString(item.hurdle),
    expectedExcess: readString(item.expected_excess),
    forwardCagr: readString(item.forward_fundamental_cagr),
    currentPrice: readString(item.current_price),
    priceStatus: readString(item.price_status),
    priceEffectiveAt: readString(item.price_effective_at),
    priceReason: readString(item.price_unavailable_reason),
    irrReason: readString(item.irr_unavailable_reason),
    methodology: method as ReturnMethodology | null,
  };
}

function methodFor(value: unknown): ModelMethod | null {
  if (value === "UFCF_DCF_10Y_FADE") return value;
  if (value === "OWNER_CASH_FLOW_10Y") return value;
  if (value === "RESIDUAL_INCOME_10Y_FADE") return value;
  return null;
}

function driverValue(
  label: string,
  value: unknown,
  kind: Driver["kind"] = "amount",
): Driver {
  return { label, value: readString(value), kind };
}

function driversFor(
  method: ModelMethod,
  revision: unknown,
  scenarioName: ScenarioName = "BASE",
): Driver[] {
  const revisionRecord = readRecord(revision);
  if (!revisionRecord) return [];
  const base = readRecord(revisionRecord.base);
  const scenario = readArray(revisionRecord.scenarios).find(
    (item) => item.scenario === scenarioName,
  );
  const years = readArray(scenario?.years);
  const firstYear = years[0];
  if (method === "UFCF_DCF_10Y_FADE") {
    return [
      driverValue("Base revenue · bn", base?.base_revenue),
      driverValue("Base EBIT margin", base?.base_ebit_margin, "ratio"),
      driverValue("Net cash / (debt) · bn", base?.net_cash_debt),
      driverValue("Diluted shares · bn", base?.diluted_shares),
      driverValue(
        `${scenarioName} terminal growth`,
        scenario?.terminal_growth,
        "ratio",
      ),
      driverValue(
        `${scenarioName} Year 1 growth`,
        firstYear?.revenue_growth,
        "ratio",
      ),
      driverValue(
        `${scenarioName} discount rate`,
        firstYear?.discount_rate,
        "ratio",
      ),
    ];
  }
  if (method === "OWNER_CASH_FLOW_10Y") {
    return [
      driverValue("Base revenue · bn", base?.base_revenue),
      driverValue("Net cash · bn", base?.net_cash),
      driverValue("Diluted shares · bn", base?.diluted_shares),
      driverValue(
        `${scenarioName} required return`,
        scenario?.required_return,
        "ratio",
      ),
      driverValue(
        `${scenarioName} terminal growth`,
        scenario?.terminal_growth,
        "ratio",
      ),
      driverValue(
        `${scenarioName} Year 1 revenue growth`,
        firstYear?.revenue_growth,
        "ratio",
      ),
      driverValue(
        `${scenarioName} Year 1 owner CF margin`,
        firstYear?.owner_cash_flow_margin,
        "ratio",
      ),
    ];
  }
  return [
    driverValue("Book value / share", base?.current_book_value_per_share),
    driverValue("Payout ratio", base?.payout_ratio, "ratio"),
    driverValue(
      `${scenarioName} starting ROE`,
      scenario?.starting_roe,
      "ratio",
    ),
    driverValue(
      `${scenarioName} cost of equity`,
      scenario?.cost_of_equity,
      "ratio",
    ),
    driverValue(
      `${scenarioName} terminal growth`,
      scenario?.terminal_growth,
      "ratio",
    ),
    driverValue(`${scenarioName} mature ROE`, scenario?.mature_roe, "ratio"),
  ];
}

function nativeDescriptor(
  model: FinancialModel | ExtendedFinancialModel,
  current: Record<string, unknown> | undefined,
): ModelDescriptor {
  const modelRecord = model as unknown as Record<string, unknown>;
  const revision = readRecord(modelRecord.current_revision);
  const listing = readRecord(modelRecord.valuation_listing);
  const method = methodFor(modelRecord.model_type);
  const currentOutput = outputView(current?.outputs);
  const acceptedOutput = outputView(revision?.outputs);
  const output = currentOutput ?? acceptedOutput;
  return {
    key: `native:${modelRecord.id as string}`,
    native: true,
    method,
    modelId: readString(modelRecord.id),
    name: readString(modelRecord.model_name) ?? "Accepted model",
    ticker: readString(listing?.ticker),
    venue: readString(listing?.venue),
    listingCurrency: readString(listing?.currency),
    currency: readString(modelRecord.model_currency),
    revisionNumber: readNumber(revision?.revision_number),
    effectiveAt: readString(revision?.effective_at),
    recordedAt: readString(revision?.recorded_at),
    actor: readString(revision?.actor),
    source: readString(revision?.source),
    rationale: readString(revision?.rationale),
    output,
    driverSets: method
      ? {
          BEAR: driversFor(method, revision, "BEAR"),
          BASE: driversFor(method, revision, "BASE"),
          BULL: driversFor(method, revision, "BULL"),
        }
      : { BEAR: [], BASE: [], BULL: [] },
  };
}

function importedDescriptor(snapshot: unknown): ModelDescriptor | null {
  const item = readRecord(snapshot);
  if (!item) return null;
  const modelKey = readString(item.model_key);
  if (!modelKey) return null;
  return {
    key: `imported:${readString(item.id) ?? modelKey}`,
    native: false,
    method: null,
    modelId: null,
    name: `Imported output · ${modelKey}`,
    ticker: null,
    venue: null,
    listingCurrency: null,
    currency: readString(item.model_currency),
    revisionNumber: null,
    effectiveAt: readString(item.effective_at),
    recordedAt: readString(item.recorded_at),
    actor: readString(item.actor),
    source: readString(item.source),
    rationale: readString(item.rationale),
    output: outputView(item),
    driverSets: { BEAR: [], BASE: [], BULL: [] },
  };
}

function methodDisplay(method: ModelMethod | null) {
  return method ? methodLabels[method] : "Imported output snapshot";
}

function formatOutputValue(value: string | null, currency: string | null) {
  return formatCurrency(value, currency, 2, "Unavailable");
}

export function formatRatioValue(value: string | null) {
  return formatPercent(value, 1, "Unavailable");
}

export function scenarioWidth(value: string | null) {
  const number = readNumber(value);
  if (number === null) return 0;
  return Math.max(0, Math.min(100, number * 100));
}

function scenarioOutput(
  output: OutputView,
  scenario: ScenarioName,
): { value: string | null; probability: string | null } {
  if (scenario === "BEAR")
    return { value: output.bearFv, probability: output.bearProbability };
  if (scenario === "BULL")
    return { value: output.bullFv, probability: output.bullProbability };
  return { value: output.baseFv, probability: output.baseProbability };
}

function ScenarioComparison({ descriptor }: { descriptor: ModelDescriptor }) {
  const [selected, setSelected] = useState<ScenarioName>("BASE");
  const output = descriptor.output;
  if (!output) return null;
  const selectedOutput = scenarioOutput(output, selected);
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Scenario range</CardTitle>
        <p className="text-sm text-muted-foreground">
          Fair values and probabilities come from the accepted revision. They
          are separate economic cases, not a blended scenario IRR.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className="grid gap-2 sm:grid-cols-3"
          role="group"
          aria-label="Valuation scenarios"
        >
          {scenarioNames.map((scenario) => {
            const item = scenarioOutput(output, scenario);
            return (
              <button
                key={scenario}
                type="button"
                aria-pressed={selected === scenario}
                onClick={() => setSelected(scenario)}
                className={`rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selected === scenario ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold">{scenario}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatRatioValue(item.probability)}
                  </span>
                </div>
                <div
                  className="mt-3 h-1.5 rounded-full bg-muted"
                  aria-hidden="true"
                >
                  <div
                    className="h-1.5 rounded-full bg-primary"
                    style={{ width: `${scenarioWidth(item.probability)}%` }}
                  />
                </div>
                <p className="mt-3 text-lg font-semibold tabular-nums">
                  {formatOutputValue(item.value, output.modelCurrency)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Fair value / share
                </p>
              </button>
            );
          })}
        </div>
        <div className="rounded-lg border bg-muted/30 p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">{selected} assumptions</span>
            <Badge variant="outline">
              Probability {formatRatioValue(selectedOutput.probability)}
            </Badge>
          </div>
          {descriptor.driverSets[selected].length > 0 ? (
            <dl className="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
              {descriptor.driverSets[selected].map((driver) => (
                <div key={driver.label} className="min-w-0">
                  <dt className="text-xs text-muted-foreground">
                    {driver.label}
                  </dt>
                  <dd className="mt-0.5 break-words text-sm font-medium tabular-nums">
                    {driver.value === null
                      ? "Unavailable"
                      : driver.kind === "ratio"
                        ? formatRatioValue(driver.value)
                        : quantity(driver.value)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              Assumptions are not retained in this imported output snapshot.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ValuationSummary({ descriptor }: { descriptor: ModelDescriptor }) {
  const output = descriptor.output;
  const currency = output?.modelCurrency ?? descriptor.currency;
  const methodology = output?.methodology;
  return (
    <Card className="min-w-0 border-primary/20 shadow-none">
      <CardHeader className="gap-3 pb-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-lg">Accepted valuation</CardTitle>
            <StatusIndicator status={output?.status ?? "UNAVAILABLE"} />
          </div>
          <p className="mt-1 break-words text-sm text-muted-foreground">
            {descriptor.name} · {methodDisplay(descriptor.method)} ·{" "}
            {currency ?? "Currency unavailable"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {descriptor.revisionNumber !== null && (
            <Badge variant="outline">
              Revision {descriptor.revisionNumber}
            </Badge>
          )}
          <Badge variant="secondary">
            {descriptor.native ? "Native · editable" : "Imported · read-only"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!output ? (
          <EmptyState
            title="Valuation unavailable"
            description="No normalized output is available for the selected model family."
          />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Bear fair value / share"
                value={formatOutputValue(output.bearFv, currency)}
                note="Accepted scenario"
              />
              <MetricCard
                label="Base fair value / share"
                value={formatOutputValue(output.baseFv, currency)}
                note="Accepted scenario"
              />
              <MetricCard
                label="Bull fair value / share"
                value={formatOutputValue(output.bullFv, currency)}
                note="Accepted scenario"
              />
              <MetricCard
                label="Weighted fair value / share"
                value={formatOutputValue(output.weightedFv, currency)}
                note="Probability-weighted reference"
              />
              <MetricCard
                label="Current exact-listing price"
                value={formatOutputValue(output.currentPrice, currency)}
                note={
                  descriptor.ticker && descriptor.venue
                    ? `${descriptor.ticker} · ${descriptor.venue} · ${descriptor.listingCurrency ?? currency ?? "currency unavailable"}`
                    : "Exact listing basis not retained"
                }
              />
              <MetricCard
                label="Valuation gap / weighted upside"
                value={formatRatioValue(output.weightedUpside)}
                note="Provided by the canonical model output"
                tone={
                  output.weightedUpside !== null &&
                  Number(output.weightedUpside) >= 0
                    ? "positive"
                    : "default"
                }
              />
              <MetricCard
                label={
                  methodology?.perspective === "ENTERPRISE"
                    ? "Expected cash-flow IRR · enterprise basis"
                    : "Expected shareholder cash-flow IRR"
                }
                value={formatRatioValue(output.expectedIrr)}
                note={
                  output.irrReason ??
                  methodology?.limitation ??
                  "Return availability follows the model methodology."
                }
              />
              <MetricCard
                label="Hurdle · expected excess"
                value={`${formatRatioValue(output.hurdle)} · ${formatRatioValue(output.expectedExcess)}`}
                note="Required return and excess are separate measures."
              />
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-3 text-xs text-muted-foreground">
              <span>Methodology: {methodology?.title ?? "Not classified"}</span>
              <span>Perspective: {methodology?.perspective ?? "Unknown"}</span>
              <span>Price state: {statusLabel(output.priceStatus)}</span>
              <span>
                Price date:{" "}
                {output.priceEffectiveAt
                  ? dateTime(output.priceEffectiveAt)
                  : "Unavailable"}
              </span>
              <span>
                Revision effective:{" "}
                {descriptor.effectiveAt
                  ? dateTime(descriptor.effectiveAt)
                  : "Unavailable"}
              </span>
            </div>
            {(output.priceReason || output.irrReason) && (
              <p className="rounded-md border border-warning/30 bg-warning/5 p-3 text-xs leading-5 text-muted-foreground">
                {output.priceReason ?? output.irrReason}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function MethodSelector({
  descriptors,
  selected,
  onSelect,
}: {
  descriptors: ModelDescriptor[];
  selected: ModelMethod | null;
  onSelect: (method: ModelMethod) => void;
}) {
  return (
    <Card className="min-w-0 shadow-none">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Canonical financial models</CardTitle>
        <p className="text-sm text-muted-foreground">
          Select the applicable methodology before opening its assumptions. The
          application keeps enterprise UFCF and equity methods distinct.
        </p>
      </CardHeader>
      <CardContent className="grid gap-2 md:grid-cols-3">
        {methodOrder.map((method) => {
          const model = descriptors.find(
            (item) => item.method === method && item.native,
          );
          return (
            <button
              key={method}
              type="button"
              aria-pressed={selected === method}
              onClick={() => onSelect(method)}
              className={`rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selected === method ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{methodLabels[method]}</span>
                <StatusIndicator
                  status={model ? model.output?.status : "NOT_MIGRATED"}
                  label={model ? "Accepted" : "Not accepted"}
                />
              </div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {methodDescriptions[method]}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                {model
                  ? `${model.name} · revision ${model.revisionNumber ?? "—"}`
                  : "Choose this method to start a supported model."}
              </p>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}

function modelDescriptors(
  dcfModels: FinancialModel[] | undefined,
  archetypeModels: ExtendedFinancialModel[] | undefined,
  currentCalculations: Record<string, unknown>[],
  imported: CompanyModelOutputsCurrent | undefined,
): ModelDescriptor[] {
  const calculations = new Map(
    currentCalculations
      .map((item) => [readString(item.model_id), item] as const)
      .filter(
        (item): item is readonly [string, Record<string, unknown>] =>
          item[0] !== null,
      ),
  );
  const native = [
    ...(dcfModels ?? []).map((model) =>
      nativeDescriptor(model, calculations.get(model.id)),
    ),
    ...(archetypeModels ?? []).map((model) =>
      nativeDescriptor(model, calculations.get(model.id)),
    ),
  ];
  if (native.length > 0) return native;
  return (imported?.models ?? [])
    .map((model) => importedDescriptor(model.snapshot))
    .filter((model): model is ModelDescriptor => model !== null);
}

export function CompanyValuationWorkspace({
  companyId,
  listings,
}: {
  companyId: string;
  listings: Listing[];
}) {
  const dcfState = useResearch(
    `companies/${encodeURIComponent(companyId)}/financial-models`,
    isFinancialModels,
  );
  const archetypeState = useResearch(
    `companies/${encodeURIComponent(companyId)}/canonical-financial-models`,
    isExtendedFinancialModels,
  );
  const outputState = useResearch(
    `companies/${encodeURIComponent(companyId)}/model-outputs/current`,
    isCompanyModelOutputsCurrent,
  );
  const returnState = useResearch(
    `companies/${encodeURIComponent(companyId)}/expected-return-history`,
    isCompanyExpectedReturnHistory,
  );
  const [selectedKey, setSelectedKey] = useState("");
  const [newMethod, setNewMethod] = useState<ModelMethod | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);

  const descriptors = useMemo(
    () =>
      modelDescriptors(
        dcfState.data,
        archetypeState.data,
        (returnState.data?.current_calculations ?? []) as unknown as Record<
          string,
          unknown
        >[],
        outputState.data,
      ),
    [dcfState.data, archetypeState.data, outputState.data, returnState.data],
  );

  const resolvedSelectedKey =
    selectedKey.startsWith("new:") ||
    descriptors.some((descriptor) => descriptor.key === selectedKey)
      ? selectedKey
      : (descriptors[0]?.key ?? "");
  const selectedDescriptor =
    descriptors.find((descriptor) => descriptor.key === resolvedSelectedKey) ??
    null;
  const selectedMethod = selectedDescriptor?.method ?? newMethod;
  const nativeSelected = selectedMethod
    ? (descriptors.find(
        (descriptor) =>
          descriptor.method === selectedMethod && descriptor.native,
      ) ?? null)
    : null;
  const activeDescriptor = nativeSelected ?? selectedDescriptor;
  const loading =
    !dcfState.data &&
    !dcfState.error &&
    !archetypeState.data &&
    !archetypeState.error &&
    !outputState.data &&
    !outputState.error &&
    !returnState.data &&
    !returnState.error;
  const partialErrors = [
    dcfState.error,
    archetypeState.error,
    outputState.error,
    returnState.error,
  ].filter(Boolean);

  const chooseMethod = (method: ModelMethod) => {
    const existing = descriptors.find(
      (descriptor) => descriptor.method === method && descriptor.native,
    );
    setSelectedKey(existing?.key ?? `new:${method}`);
    setNewMethod(method);
    setEditorOpen(false);
  };

  const editorListings = listings;
  const selectedMethodLabel = selectedMethod
    ? methodLabels[selectedMethod]
    : "supported model";

  return (
    <section
      id="valuation-workspace"
      aria-labelledby="valuation-workspace-title"
      className="space-y-6"
    >
      <PageSection
        title="Valuation workspace"
        description="Understand the accepted value range first, then open the applicable assumptions and deterministic preview when you need to underwrite a change."
        id="valuation-workspace-title"
      >
        {loading ? (
          <PendingOrError
            error={undefined}
            retry={() => {
              dcfState.retry();
              archetypeState.retry();
              outputState.retry();
              returnState.retry();
            }}
          />
        ) : activeDescriptor ? (
          <div className="space-y-4">
            <ValuationSummary descriptor={activeDescriptor} />
            <div className="grid min-w-0 gap-4 xl:grid-cols-[1.5fr_1fr]">
              <ScenarioComparison descriptor={activeDescriptor} />
              <Card className="min-w-0 shadow-none">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Method & evidence</CardTitle>
                  <p className="text-sm text-muted-foreground">
                    The return basis and revision provenance stay visible beside
                    the conclusion.
                  </p>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <dl className="space-y-2">
                    <div className="flex flex-wrap justify-between gap-2 border-b pb-2">
                      <dt className="text-muted-foreground">Methodology</dt>
                      <dd className="text-right font-medium">
                        {activeDescriptor.output?.methodology?.title ??
                          methodDisplay(activeDescriptor.method)}
                      </dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2 border-b pb-2">
                      <dt className="text-muted-foreground">
                        Comparability group
                      </dt>
                      <dd className="text-right font-medium">
                        {activeDescriptor.output?.methodology
                          ?.comparability_group ?? "Not classified"}
                      </dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2 border-b pb-2">
                      <dt className="text-muted-foreground">
                        Accepted revision
                      </dt>
                      <dd className="text-right font-medium">
                        {activeDescriptor.revisionNumber === null
                          ? "Imported snapshot"
                          : `${activeDescriptor.revisionNumber} · ${activeDescriptor.effectiveAt ? dateTime(activeDescriptor.effectiveAt) : "date unavailable"}`}
                      </dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2">
                      <dt className="text-muted-foreground">Source</dt>
                      <dd className="max-w-[24rem] break-words text-right font-medium">
                        {activeDescriptor.source ?? "Not recorded"}
                      </dd>
                    </div>
                  </dl>
                  {activeDescriptor.output?.methodology?.limitation && (
                    <p className="rounded-md border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
                      {activeDescriptor.output.methodology.limitation}
                    </p>
                  )}
                  {activeDescriptor.rationale && (
                    <p className="border-t pt-3 text-xs leading-5">
                      {activeDescriptor.rationale}
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No valuation is available"
            description="No accepted native model or normalized imported output is mapped to this company. Missing valuation data is kept explicit."
          />
        )}
      </PageSection>

      {partialErrors.length > 0 && !loading && (
        <p className="rounded-md border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">
          Some model sources are unavailable. The displayed state uses only the
          verified responses that loaded; no missing output is treated as zero.
        </p>
      )}

      {!loading && (
        <PageSection
          title="Model family"
          description="Choose the supported methodology that matches the business. Unaccepted methods remain separate until explicitly selected."
          id="canonical-model-selector"
        >
          <MethodSelector
            descriptors={descriptors}
            selected={selectedMethod}
            onSelect={chooseMethod}
          />
        </PageSection>
      )}

      {!loading && selectedMethod && (
        <Card className="min-w-0 border-primary/20 shadow-none">
          <CardHeader className="gap-3 pb-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle className="text-base">
                {nativeSelected
                  ? "Draft assumptions & deterministic preview"
                  : `Start ${methodLabels[selectedMethod]} model`}
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Accepted model → draft assumptions → API recalculation → compare
                impacts → review evidence → explicit acceptance.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {nativeSelected ||
              selectedDescriptor?.native === false ||
              !activeDescriptor ? (
                <Button
                  type="button"
                  variant={editorOpen ? "secondary" : "default"}
                  onClick={() => setEditorOpen((open) => !open)}
                >
                  {editorOpen
                    ? "Close editor"
                    : nativeSelected
                      ? "Edit accepted assumptions"
                      : `Start ${selectedMethodLabel} model`}
                </Button>
              ) : null}
            </div>
          </CardHeader>
          {editorOpen && (
            <CardContent className="space-y-4 border-t pt-4">
              {selectedMethod === "UFCF_DCF_10Y_FADE" && (
                <CanonicalDcfExplorer
                  companyId={companyId}
                  listings={editorListings}
                />
              )}
              {selectedMethod === "OWNER_CASH_FLOW_10Y" && (
                <CanonicalArchetypeExplorer
                  companyId={companyId}
                  listings={editorListings}
                  focusedKind="owner-cash-flow"
                />
              )}
              {selectedMethod === "RESIDUAL_INCOME_10Y_FADE" && (
                <CanonicalArchetypeExplorer
                  companyId={companyId}
                  listings={editorListings}
                  focusedKind="residual-income"
                />
              )}
            </CardContent>
          )}
        </Card>
      )}

      <div className="rounded-xl border bg-card">
        <button
          type="button"
          aria-expanded={auditOpen}
          onClick={() => setAuditOpen((open) => !open)}
          className="flex min-h-12 w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:px-5"
        >
          <span>Revision history & migration diagnostics</span>
          <span aria-hidden="true" className="text-muted-foreground">
            {auditOpen ? "−" : "+"}
          </span>
        </button>
        {auditOpen && (
          <div className="space-y-6 border-t p-4 sm:p-5">
            <ModelMigrationStatus companyId={companyId} />
            <CompanyModelOutputHistory companyId={companyId} />
          </div>
        )}
      </div>
    </section>
  );
}
