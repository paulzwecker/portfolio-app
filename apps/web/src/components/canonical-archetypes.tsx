"use client";

import { useId, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/components/research-frame";
import {
  isAdditionalModelContractImport,
  isAdditionalModelContractPreview,
  isAdditionalModelPortableContractResponse,
  isExtendedFinancialModels,
  isExtendedFinancialModel,
  isOwnerCashFlowCalculationPreview,
  isResidualIncomeCalculationPreview,
  type AdditionalModelPortableContract,
  type AdditionalModelContractPreview,
  type ExtendedFinancialModel,
  type FinancialModelCalculationOutputs,
  type OwnerCashFlowInput,
  type OwnerCashFlowCalculationPreview,
  type OwnerCashFlowRevisionRead,
  type ResidualIncomeInput,
  type ResidualIncomeCalculationPreview,
  type ResidualIncomeRevisionRead,
} from "@/lib/domain-contracts";

type Kind = "owner-cash-flow" | "residual-income";
type Input = OwnerCashFlowInput | ResidualIncomeInput;
type OutputView = Pick<
  FinancialModelCalculationOutputs,
  | "bear_fv"
  | "base_fv"
  | "bull_fv"
  | "weighted_fv"
  | "expected_cash_flow_irr"
  | "hurdle"
  | "weighted_upside"
  | "expected_excess"
>;
type Listing = {
  id: string;
  ticker: string;
  venue: string;
  currency?: string | null;
};
type Draft = {
  model: ExtendedFinancialModel | null;
  kind: Kind;
  input: Input;
  listing: string;
  currency: string;
  name: string;
  rationale: string;
  source: string;
  preview:
    OwnerCashFlowCalculationPreview | ResidualIncomeCalculationPreview | null;
};
type ContractDraft = { id: string; value: AdditionalModelPortableContract };
const cases = ["BEAR", "BASE", "BULL"] as const;

const emptyOwner = (): OwnerCashFlowInput => ({
  base: { base_revenue: "", net_cash: "", diluted_shares: "" },
  scenarios: cases.map((scenario, i) => ({
    scenario,
    probability: ["0.2", "0.6", "0.2"][i],
    required_return: "",
    terminal_growth: "",
    rationale: "",
    years: Array.from({ length: 10 }, (_, year) => ({
      forecast_year: year + 1,
      revenue_growth: "",
      owner_cash_flow_margin: "",
    })),
  })),
});
const emptyResidual = (): ResidualIncomeInput => ({
  base: { current_book_value_per_share: "", payout_ratio: "" },
  scenarios: cases.map((scenario, i) => ({
    scenario,
    probability: ["0.28", "0.56", "0.16"][i],
    starting_roe: "",
    cost_of_equity: "",
    terminal_growth: "",
    mature_roe: "",
    rationale: "",
  })),
});

function InputField({
  fieldId,
  label,
  value,
  onChange,
}: {
  fieldId?: string;
  label: string;
  value: string | number;
  onChange: (value: string) => void;
}) {
  const generatedId = useId().replaceAll(":", "");
  const id =
    fieldId ??
    `${generatedId}-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 tabular-nums"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function OutputValues({ output }: { output: OutputView }) {
  const rows = [
    ["Bear FV", output.bear_fv, false],
    ["Base FV", output.base_fv, false],
    ["Bull FV", output.bull_fv, false],
    ["Weighted FV", output.weighted_fv, false],
    ["Expected IRR", output.expected_cash_flow_irr, true],
    ["Hurdle", output.hurdle, true],
    ["Upside", output.weighted_upside, true],
    ["Expected excess", output.expected_excess, true],
  ] as const;
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {rows.map(([name, value, ratio]) => (
        <div key={name} className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">{name}</dt>
          <dd className="mt-1 font-mono text-sm font-semibold tabular-nums">
            {value === null
              ? "Unavailable"
              : ratio
                ? (Number(value) * 100).toFixed(1) + "%"
                : Number(value).toFixed(2)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ModelOutputs({ model }: { model: ExtendedFinancialModel }) {
  return <OutputValues output={model.current_revision.outputs} />;
}

function DraftProjection({
  kind,
  preview,
}: {
  kind: Kind;
  preview: Draft["preview"];
}) {
  if (!preview) return null;
  const rows = preview.projections.filter((row) => row.scenario === "BASE");
  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full min-w-[38rem] text-left text-xs tabular-nums">
        <caption className="px-3 py-2 text-left font-medium">
          Base-case projection preview
        </caption>
        <thead className="border-y bg-muted/50 text-muted-foreground">
          {kind === "owner-cash-flow" ? (
            <tr>
              <th className="p-2">Year</th>
              <th className="p-2">Revenue</th>
              <th className="p-2">Owner CF/share</th>
              <th className="p-2">PV/share</th>
            </tr>
          ) : (
            <tr>
              <th className="p-2">Year</th>
              <th className="p-2">ROE</th>
              <th className="p-2">EPS/share</th>
              <th className="p-2">Dividend/share</th>
              <th className="p-2">Ending BV/share</th>
              <th className="p-2">Residual income</th>
            </tr>
          )}
        </thead>
        <tbody>
          {rows.map((row) =>
            kind === "owner-cash-flow" ? (
              <tr key={row.forecast_year} className="border-b last:border-0">
                <td className="p-2">{row.forecast_year}</td>
                <td className="p-2">
                  {"revenue" in row ? Number(row.revenue).toFixed(2) : "—"}
                </td>
                <td className="p-2">
                  {"owner_cash_flow_per_share" in row
                    ? Number(row.owner_cash_flow_per_share).toFixed(2)
                    : "—"}
                </td>
                <td className="p-2">
                  {"present_value_per_share" in row
                    ? Number(row.present_value_per_share).toFixed(2)
                    : "—"}
                </td>
              </tr>
            ) : (
              <tr key={row.forecast_year} className="border-b last:border-0">
                <td className="p-2">{row.forecast_year}</td>
                <td className="p-2">
                  {"return_on_equity" in row
                    ? (Number(row.return_on_equity) * 100).toFixed(1) + "%"
                    : "—"}
                </td>
                <td className="p-2">
                  {"net_income_per_share" in row
                    ? Number(row.net_income_per_share).toFixed(2)
                    : "—"}
                </td>
                <td className="p-2">
                  {"dividend_per_share" in row
                    ? Number(row.dividend_per_share).toFixed(2)
                    : "—"}
                </td>
                <td className="p-2">
                  {"ending_book_value_per_share" in row
                    ? Number(row.ending_book_value_per_share).toFixed(2)
                    : "—"}
                </td>
                <td className="p-2">
                  {"residual_income_per_share" in row
                    ? Number(row.residual_income_per_share).toFixed(2)
                    : "—"}
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </div>
  );
}

function currentInput(model: ExtendedFinancialModel): Input {
  if (model.model_type === "OWNER_CASH_FLOW_10Y") {
    const value = model.current_revision as OwnerCashFlowRevisionRead;
    return { base: value.base, scenarios: value.scenarios };
  }
  const value = model.current_revision as ResidualIncomeRevisionRead;
  return { base: value.base, scenarios: value.scenarios };
}

export function CanonicalArchetypeExplorer({
  companyId,
  listings,
}: {
  companyId: string;
  listings: Listing[];
}) {
  const state = useResearch(
    "companies/" +
      encodeURIComponent(companyId) +
      "/canonical-financial-models",
    isExtendedFinancialModels,
  );
  const models = state.data ?? [];
  const [draft, setDraft] = useState<Draft | null>(null);
  const [contract, setContract] = useState<ContractDraft | null>(null);
  const [contractPreview, setContractPreview] =
    useState<AdditionalModelContractPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const begin = (kind: Kind, model: ExtendedFinancialModel | null = null) => {
    const first = listings[0];
    setError(null);
    setMessage(null);
    setDraft({
      model,
      kind,
      input: model
        ? currentInput(model)
        : kind === "owner-cash-flow"
          ? emptyOwner()
          : emptyResidual(),
      listing: model?.valuation_listing.id ?? first?.id ?? "",
      currency: model?.model_currency ?? "",
      name:
        model?.model_name ??
        (kind === "owner-cash-flow"
          ? "Owner cash-flow model"
          : "Residual-income model"),
      rationale: "",
      source: "Company Explorer",
      preview: null,
    });
  };

  const base = (field: string, value: string) => {
    setDraft((old) => {
      if (!old) return old;
      const next = { ...old.input.base, [field]: value };
      return {
        ...old,
        input: { ...old.input, base: next } as Input,
        preview: null,
      };
    });
  };
  const scenario = (i: number, field: string, value: string, year?: number) => {
    setDraft((old) => {
      if (!old) return old;
      const input = old.input;
      const items = [...input.scenarios];
      if (old.kind === "owner-cash-flow") {
        const owner = input as OwnerCashFlowInput;
        const item = { ...owner.scenarios[i] };
        if (year === undefined) Object.assign(item, { [field]: value });
        else {
          const years = [...item.years];
          years[year] = { ...years[year], [field]: value };
          item.years = years;
        }
        items[i] = item;
      } else {
        const residual = input as ResidualIncomeInput;
        items[i] = { ...residual.scenarios[i], [field]: value };
      }
      return {
        ...old,
        input: { ...input, scenarios: items } as Input,
        preview: null,
      };
    });
  };

  const preview = async () => {
    if (!draft) return;
    const path = draft.model
      ? "canonical-financial-models/" +
        draft.model.id +
        "/" +
        draft.kind +
        "/revisions/preview"
      : "companies/" +
        encodeURIComponent(companyId) +
        "/canonical-financial-models/" +
        draft.kind +
        "/preview";
    const body = draft.model
      ? { base_revision_id: draft.model.current_revision_id, ...draft.input }
      : {
          valuation_listing_id: draft.listing,
          model_currency: draft.currency,
          ...draft.input,
        };
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/research/" + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result: unknown = await response.json();
      const valid =
        draft.kind === "owner-cash-flow"
          ? isOwnerCashFlowCalculationPreview(result)
          : isResidualIncomeCalculationPreview(result);
      if (!response.ok || !valid) {
        setError(
          response.status === 409
            ? "The model base changed. Reload the latest revision."
            : "Check required assumptions and terminal spread, then preview again.",
        );
      } else
        setDraft((old) =>
          old
            ? {
                ...old,
                preview: result as
                  | OwnerCashFlowCalculationPreview
                  | ResidualIncomeCalculationPreview,
              }
            : old,
        );
    } catch {
      setError("Research services are unavailable. Check the API and retry.");
    } finally {
      setBusy(false);
    }
  };

  const accept = async () => {
    if (!draft || !draft.preview || !draft.rationale.trim()) return;
    const revision = {
      ...draft.input,
      base_revision_id: draft.model?.current_revision_id ?? null,
      source_revision_id: null,
      actor: "LOCAL_USER",
      source: draft.source.trim() || "Company Explorer",
      rationale: draft.rationale.trim(),
      effective_at: new Date().toISOString(),
    };
    const path = draft.model
      ? "canonical-financial-models/" +
        draft.model.id +
        "/" +
        draft.kind +
        "/revisions"
      : "companies/" +
        encodeURIComponent(companyId) +
        "/canonical-financial-models/" +
        draft.kind;
    const body = draft.model
      ? revision
      : {
          model_name: draft.name,
          valuation_listing_id: draft.listing,
          model_currency: draft.currency,
          source_model_key: null,
          initial_revision: revision,
        };
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/research/" + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result: unknown = await response.json();
      if (!response.ok || (!draft.model && !isExtendedFinancialModel(result))) {
        setError(
          response.status === 409
            ? "The model advanced while you edited. Reload before accepting."
            : "The revision could not be accepted. Check assumptions and provenance.",
        );
      } else {
        setDraft(null);
        setMessage("Accepted as a new immutable model revision.");
        state.retry();
      }
    } catch {
      setError("Research services are unavailable. Retry the acceptance.");
    } finally {
      setBusy(false);
    }
  };

  const exportContract = async (model: ExtendedFinancialModel) => {
    try {
      const response = await fetch(
        "/api/research/canonical-financial-models/" + model.id + "/contract",
      );
      const value: unknown = await response.json();
      if (!response.ok || !isAdditionalModelPortableContractResponse(value)) {
        setError("Could not export the v2 Sheets contract.");
        return;
      }
      const link = document.createElement("a");
      link.href = URL.createObjectURL(
        new Blob([JSON.stringify(value, null, 2)], {
          type: "application/json",
        }),
      );
      link.download =
        (model.source_model_key ?? model.id) + "-model-contract-v2.json";
      link.click();
      URL.revokeObjectURL(link.href);
      setContract({ id: model.id, value });
      setContractPreview(null);
    } catch {
      setError("Could not export the portable model contract.");
    }
  };

  const readContract = async (model: ExtendedFinancialModel, file?: File) => {
    if (!file) return;
    try {
      const value: unknown = JSON.parse(await file.text());
      if (
        !isAdditionalModelPortableContractResponse(value) ||
        value.model_id !== model.id
      ) {
        setError("Choose a v2 contract exported from this model.");
        return;
      }
      setContract({ id: model.id, value });
      setContractPreview(null);
    } catch {
      setError("The selected contract is not valid JSON.");
    }
  };

  const previewContract = async () => {
    if (!contract) return;
    setBusy(true);
    try {
      const response = await fetch(
        "/api/research/canonical-financial-models/" +
          contract.id +
          "/contract/preview",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(contract.value),
        },
      );
      const data: unknown = await response.json();
      if (!response.ok || !isAdditionalModelContractPreview(data)) {
        setError("The external revision could not be previewed.");
      } else setContractPreview(data);
    } catch {
      setError("Could not preview the external model update.");
    } finally {
      setBusy(false);
    }
  };

  const importContract = async () => {
    if (!contract || contractPreview?.status !== "READY") return;
    if (!contract.value.candidate_revision.rationale?.trim()) {
      setError("Add a rationale to the contract before acceptance.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(
        "/api/research/canonical-financial-models/" +
          contract.id +
          "/contract/import",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(contract.value),
        },
      );
      const data: unknown = await response.json();
      if (!response.ok || !isAdditionalModelContractImport(data)) {
        setError(
          "The external revision conflicted with current state. Export again and reconcile.",
        );
      } else {
        setContract(null);
        setContractPreview(null);
        setMessage(
          "Sheets-originated state was accepted into canonical revision history.",
        );
        state.retry();
      }
    } catch {
      setError("Could not import the external revision.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id="canonical-model-archetypes" className="mt-8 space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Additional canonical models</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Owner cash-flow and residual-income methods use separate assumptions
            and engines, with shared immutable revision and output history.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => begin("owner-cash-flow")}>
            New owner cash-flow model
          </Button>
          <Button variant="outline" onClick={() => begin("residual-income")}>
            New residual-income model
          </Button>
        </div>
      </header>
      {state.error && (
        <p role="alert" className="rounded-md border p-3 text-sm">
          Model data could not be loaded. Retry after checking API and
          migrations.
        </p>
      )}
      {message && (
        <p
          role="status"
          className="rounded-md border border-primary/40 p-3 text-sm"
        >
          {message}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 p-3 text-sm"
        >
          {error}
        </p>
      )}
      {models.length === 0 && !state.error && (
        <Card>
          <CardContent className="py-5 text-sm text-muted-foreground">
            No additional-method model is accepted for this company. Create a
            method-specific model or import a reviewed v2 contract.
          </CardContent>
        </Card>
      )}
      {models.map((model) => (
        <Card key={model.id}>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle>{model.model_name}</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {model.model_type === "OWNER_CASH_FLOW_10Y"
                    ? "Owner cash flow"
                    : "Residual income"}{" "}
                  · {model.valuation_listing.ticker} · {model.model_currency}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() =>
                    begin(
                      model.model_type === "OWNER_CASH_FLOW_10Y"
                        ? "owner-cash-flow"
                        : "residual-income",
                      model,
                    )
                  }
                >
                  Edit assumptions
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => void exportContract(model)}
                >
                  Export Sheets contract
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">
                Revision {model.current_revision.revision_number}
              </Badge>
              <Badge
                variant={
                  model.current_revision.outputs.status === "COMPLETE"
                    ? "default"
                    : "secondary"
                }
              >
                {model.current_revision.outputs.status}
              </Badge>
              <span className="text-xs text-muted-foreground">
                Recorded{" "}
                {new Date(model.current_revision.recorded_at).toLocaleString()}{" "}
                · {model.current_revision.actor}
              </span>
            </div>
            <ModelOutputs model={model} />
            {model.current_revision.outputs.status === "PARTIAL" && (
              <p className="text-xs text-muted-foreground">
                Price-dependent results are explicitly unavailable:{" "}
                {model.current_revision.outputs.price_unavailable_reason ??
                  model.current_revision.outputs.irr_unavailable_reason}
              </p>
            )}
            <p className="text-sm">{model.current_revision.rationale}</p>
            <details className="rounded-md border px-3">
              <summary className="cursor-pointer py-3 text-sm font-medium">
                Revision history ({model.history.length})
              </summary>
              <ul className="space-y-3 pb-3">
                {model.history.map((revision) => (
                  <li key={revision.id} className="border-t pt-3">
                    <p className="text-sm font-medium">
                      Revision {revision.revision_number} ·{" "}
                      {new Date(revision.recorded_at).toLocaleString()}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {revision.rationale}
                    </p>
                    <div className="mt-3">
                      <OutputValues output={revision.outputs} />
                    </div>
                  </li>
                ))}
              </ul>
            </details>
            <details className="rounded-md border px-3">
              <summary className="cursor-pointer py-3 text-sm font-medium">
                Sheets and external authoring
              </summary>
              <div className="space-y-3 pb-4">
                <p className="text-xs text-muted-foreground">
                  Portable contract v2 exports method-specific assumptions.
                  Preview shows input and output differences; stale bases are
                  rejected.
                </p>
                <label className="block space-y-1.5 text-sm">
                  <span className="font-medium">Candidate contract JSON</span>
                  <input
                    type="file"
                    accept="application/json,.json"
                    className="block w-full text-sm"
                    onChange={(event) =>
                      void readContract(model, event.target.files?.[0])
                    }
                  />
                </label>
                {contract?.id === model.id && (
                  <>
                    <label className="block space-y-1.5 text-sm">
                      <span className="font-medium">
                        External revision rationale
                      </span>
                      <textarea
                        className="min-h-20 w-full rounded-md border bg-background p-3 text-sm"
                        value={
                          contract.value.candidate_revision.rationale ?? ""
                        }
                        onChange={(event) => {
                          setContract({
                            ...contract,
                            value: {
                              ...contract.value,
                              candidate_revision: {
                                ...contract.value.candidate_revision,
                                rationale: event.target.value,
                              },
                            },
                          });
                          setContractPreview(null);
                        }}
                      />
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => void previewContract()}
                      >
                        Preview external update
                      </Button>
                      <Button
                        disabled={busy || contractPreview?.status !== "READY"}
                        onClick={() => void importContract()}
                      >
                        Accept imported revision
                      </Button>
                    </div>
                    {contractPreview && (
                      <div className="rounded-md border p-3 text-sm">
                        <Badge
                          variant={
                            contractPreview.status === "READY"
                              ? "default"
                              : "secondary"
                          }
                        >
                          {contractPreview.status}
                        </Badge>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {contractPreview.reason ??
                            "Review the input and output changes before acceptance."}
                        </p>
                        <p className="mt-2">
                          {contractPreview.changes.length} assumption field(s)
                          changed and {contractPreview.output_changes.length}{" "}
                          normalized output(s) changed.
                        </p>
                        {contractPreview.changes.length > 0 && (
                          <ul className="mt-2 max-h-40 space-y-1 overflow-auto font-mono text-xs">
                            {contractPreview.changes.map((change) => (
                              <li key={change.path}>
                                {change.path}: {change.previous ?? "missing"} →{" "}
                                {change.proposed ?? "missing"}
                              </li>
                            ))}
                          </ul>
                        )}
                        <div className="mt-3">
                          <OutputValues
                            output={contractPreview.current_outputs}
                          />
                        </div>
                        {contractPreview.calculated_outputs && (
                          <div className="mt-3">
                            <p className="mb-2 text-xs font-medium">
                              Recalculated candidate outputs
                            </p>
                            <OutputValues
                              output={contractPreview.calculated_outputs}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </details>
          </CardContent>
        </Card>
      ))}

      {draft && (
        <Card>
          <CardHeader>
            <CardTitle>
              {draft.model ? "Revise" : "Create"}{" "}
              {draft.kind === "owner-cash-flow"
                ? "owner-cash-flow"
                : "residual-income"}{" "}
              model
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Enter ratios as decimals: 0.12 means 12%. Each method has its own
              calculation and projection structure.
            </p>
          </CardHeader>
          <CardContent>
            <div className="space-y-5">
              {!draft.model && (
                <div className="grid gap-3 sm:grid-cols-3">
                  <InputField
                    label="Model name"
                    value={draft.name}
                    onChange={(name) => setDraft({ ...draft, name })}
                  />
                  <div className="space-y-1.5">
                    <label
                      htmlFor="archetype-listing"
                      className="text-sm font-medium"
                    >
                      Valuation listing
                    </label>
                    <select
                      id="archetype-listing"
                      className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                      value={draft.listing}
                      onChange={(event) => {
                        setDraft({
                          ...draft,
                          listing: event.target.value,
                          preview: null,
                        });
                      }}
                    >
                      <option value="">Choose a listing</option>
                      {listings.map((listing) => (
                        <option key={listing.id} value={listing.id}>
                          {listing.ticker} · {listing.venue} ·{" "}
                          {listing.currency ?? "currency unknown"}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <InputField
                      label="Model currency (ISO)"
                      value={draft.currency}
                      onChange={(currency) =>
                        setDraft({
                          ...draft,
                          currency: currency.toUpperCase(),
                          preview: null,
                        })
                      }
                    />
                    <p className="mt-1 text-xs text-muted-foreground">
                      Enter the model&apos;s valuation currency explicitly. No
                      FX conversion is inferred from the listing.
                    </p>
                  </div>
                </div>
              )}
              {draft.kind === "owner-cash-flow" ? (
                <div className="grid gap-3 sm:grid-cols-3">
                  <InputField
                    label="Base revenue (billions)"
                    value={
                      (draft.input as OwnerCashFlowInput).base.base_revenue
                    }
                    onChange={(v) => base("base_revenue", v)}
                  />
                  <InputField
                    label="Net cash (billions)"
                    value={(draft.input as OwnerCashFlowInput).base.net_cash}
                    onChange={(v) => base("net_cash", v)}
                  />
                  <InputField
                    label="Diluted shares (billions)"
                    value={
                      (draft.input as OwnerCashFlowInput).base.diluted_shares
                    }
                    onChange={(v) => base("diluted_shares", v)}
                  />
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  <InputField
                    label="Current book value per share"
                    value={
                      (draft.input as ResidualIncomeInput).base
                        .current_book_value_per_share
                    }
                    onChange={(v) => base("current_book_value_per_share", v)}
                  />
                  <InputField
                    label="Payout ratio"
                    value={
                      (draft.input as ResidualIncomeInput).base.payout_ratio
                    }
                    onChange={(v) => base("payout_ratio", v)}
                  />
                </div>
              )}
              {draft.input.scenarios.map((item, i) => (
                <details
                  key={item.scenario}
                  open={i === 1}
                  className="rounded-md border p-4"
                >
                  <summary className="cursor-pointer font-medium">
                    {item.scenario} scenario
                  </summary>
                  {draft.kind === "owner-cash-flow" ? (
                    <div className="mt-4 space-y-4">
                      <div className="grid gap-3 sm:grid-cols-3">
                        {(
                          [
                            "probability",
                            "required_return",
                            "terminal_growth",
                          ] as const
                        ).map((field) => (
                          <InputField
                            key={field}
                            label={field.replaceAll("_", " ")}
                            value={
                              (draft.input as OwnerCashFlowInput).scenarios[i][
                                field
                              ]
                            }
                            onChange={(v) => scenario(i, field, v)}
                          />
                        ))}
                      </div>
                      <InputField
                        label={`${item.scenario} scenario rationale`}
                        value={item.rationale}
                        onChange={(v) => scenario(i, "rationale", v)}
                      />
                      <p className="text-sm font-medium">
                        Revenue growth and owner-cash-flow margin by year
                      </p>
                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                        {(draft.input as OwnerCashFlowInput).scenarios[
                          i
                        ].years.map((year, y) => (
                          <div
                            key={year.forecast_year}
                            className="space-y-3 rounded-md border p-3"
                          >
                            <p className="text-xs font-medium text-muted-foreground">
                              Year {year.forecast_year}
                            </p>
                            <InputField
                              label="Revenue growth"
                              value={year.revenue_growth}
                              onChange={(v) =>
                                scenario(i, "revenue_growth", v, y)
                              }
                            />
                            <InputField
                              label="Owner CF margin"
                              value={year.owner_cash_flow_margin}
                              onChange={(v) =>
                                scenario(i, "owner_cash_flow_margin", v, y)
                              }
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {(
                        [
                          "probability",
                          "starting_roe",
                          "cost_of_equity",
                          "terminal_growth",
                          "mature_roe",
                        ] as const
                      ).map((field) => (
                        <InputField
                          key={field}
                          label={field.replaceAll("_", " ")}
                          value={
                            (draft.input as ResidualIncomeInput).scenarios[i][
                              field
                            ]
                          }
                          onChange={(v) => scenario(i, field, v)}
                        />
                      ))}
                      <InputField
                        label={`${item.scenario} scenario rationale`}
                        value={item.rationale}
                        onChange={(v) => scenario(i, "rationale", v)}
                      />
                      <p className="self-end text-xs text-muted-foreground">
                        ROE holds for five years, then fades linearly to mature
                        ROE by Year 10.
                      </p>
                    </div>
                  )}
                </details>
              ))}
              <div className="grid gap-3 sm:grid-cols-2">
                <InputField
                  label="Rationale"
                  value={draft.rationale}
                  onChange={(rationale) => setDraft({ ...draft, rationale })}
                />
                <InputField
                  label="Source reference or URL"
                  value={draft.source}
                  onChange={(source) => setDraft({ ...draft, source })}
                />
              </div>
              {draft.preview && (
                <div className="rounded-md border p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-medium">Draft outputs</h3>
                    <Badge variant="outline">
                      {draft.preview.outputs.status}
                    </Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Forecast projections have been calculated by the API and
                    will be stored with the accepted revision.
                  </p>
                  <div className="mt-3">
                    <OutputValues output={draft.preview.outputs} />
                  </div>
                  {draft.preview.outputs.status === "PARTIAL" && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Price-dependent outputs remain unavailable:{" "}
                      {draft.preview.outputs.price_unavailable_reason ??
                        draft.preview.outputs.irr_unavailable_reason}
                    </p>
                  )}
                  <div className="mt-4">
                    <DraftProjection
                      kind={draft.kind}
                      preview={draft.preview}
                    />
                  </div>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={busy || listings.length === 0}
                  onClick={() => void preview()}
                >
                  Preview deterministic calculation
                </Button>
                <Button
                  disabled={busy || !draft.preview || !draft.rationale.trim()}
                  onClick={() => void accept()}
                >
                  {draft.model ? "Accept new revision" : "Create model"}
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => setDraft(null)}
                >
                  Cancel
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Preview never persists state. Acceptance checks the revision
                base again, recalculates, and appends to history.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
