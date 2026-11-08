"use client";

import { useState } from "react";
import { PendingOrError } from "@/components/app/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import { isDcfSensitivity, type DcfSensitivity } from "@/lib/domain-contracts";
import { formatCurrency, formatPercent, statusLabel } from "@/lib/display";

type OutputKey = "weighted_fv" | "bear_fv" | "base_fv" | "bull_fv";
const staleRevisionMessage =
  "The accepted model changed. Reload the company before exploring sensitivity.";

export function sensitivityShiftLabel(value: string) {
  const shift = Number(value) * 100;
  return `${shift > 0 ? "+" : ""}${shift} pp`;
}

export function DcfSensitivityGrid({ data }: { data: DcfSensitivity }) {
  const [output, setOutput] = useState<OutputKey>("weighted_fv");
  const unavailable = data.cells.filter((cell) => cell.status !== "AVAILABLE");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Accepted revision {data.revision_number} · {data.methodology_version}
        </p>
        <label className="flex items-center gap-2 text-sm">
          Fair value
          <select
            aria-label="Sensitivity scenario"
            value={output}
            onChange={(event) => setOutput(event.target.value as OutputKey)}
            className="min-h-11 rounded-md border bg-background px-2"
          >
            <option value="weighted_fv">Probability-weighted</option>
            <option value="bear_fv">Bear</option>
            <option value="base_fv">Base</option>
            <option value="bull_fv">Bull</option>
          </select>
        </label>
      </div>
      <table className="w-full table-fixed border-collapse text-xs sm:text-sm">
        <caption className="mb-2 text-left text-sm font-medium">
          Fair value per share · {data.model_currency}. Columns shift terminal
          growth.
        </caption>
        <thead>
          <tr>
            <th
              scope="col"
              className="w-[28%] border p-2 text-left font-medium"
            >
              Discount rate shift
            </th>
            {data.terminal_growth_shifts.map((shift) => (
              <th scope="col" key={shift} className="border p-2 font-medium">
                {sensitivityShiftLabel(shift)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.discount_rate_shifts.map((discountShift) => (
            <tr key={discountShift}>
              <th scope="row" className="border p-2 text-left font-medium">
                {sensitivityShiftLabel(discountShift)}
              </th>
              {data.terminal_growth_shifts.map((growthShift) => {
                const cell = data.cells.find(
                  (item) =>
                    item.discount_rate_shift === discountShift &&
                    item.terminal_growth_shift === growthShift,
                );
                const baseline = discountShift === "0" && growthShift === "0";
                return (
                  <td
                    key={growthShift}
                    className={`border p-2 text-center tabular-nums [overflow-wrap:anywhere] ${baseline ? "bg-primary/10 font-semibold" : ""}`}
                    aria-label={baseline ? "Accepted assumptions" : undefined}
                  >
                    {cell?.status === "AVAILABLE"
                      ? formatCurrency(cell[output], data.model_currency)
                      : "Unavailable"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs leading-5 text-muted-foreground">
        Shaded cell uses the accepted assumptions. Shifts are percentage points
        applied to every scenario. Annual discount rates in years 1–5 move
        together; years 6–10 inherit year 5. Operating inputs, probabilities and
        the UFCF tail remain fixed. This grid shows hypothetical valuation
        references. Investor hurdle and shareholder returns require their own
        reviewed economic definitions.
      </p>
      <div className="grid gap-2 sm:grid-cols-3">
        {data.scenarios.map((scenario) => (
          <div
            key={scenario.scenario}
            className="rounded-md border p-3 text-xs"
          >
            <p className="font-medium">
              {statusLabel(scenario.scenario)} ·{" "}
              {formatPercent(scenario.probability)}
            </p>
            <p className="mt-1 text-muted-foreground">
              Accepted year-5 discount rate{" "}
              {formatPercent(scenario.year5_discount_rate)}
            </p>
            <p className="mt-1 text-muted-foreground">
              Terminal growth {formatPercent(scenario.terminal_growth)}
            </p>
          </div>
        ))}
      </div>
      {unavailable.length > 0 && (
        <div
          className="rounded-md border border-warning/30 p-3 text-xs"
          role="status"
        >
          <p className="font-medium">Unavailable rate combinations</p>
          <ul className="mt-2 space-y-2">
            {unavailable.map((cell) => (
              <li
                key={`${cell.discount_rate_shift},${cell.terminal_growth_shift}`}
              >
                Discount {sensitivityShiftLabel(cell.discount_rate_shift)},
                growth {sensitivityShiftLabel(cell.terminal_growth_shift)}.{" "}
                {cell.unavailable_reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function DcfSensitivityPanel({
  modelId,
  revisionId,
}: {
  modelId: string;
  revisionId: string;
}) {
  const [open, setOpen] = useState(false);
  const { data, error, retry } = useResearch(
    `financial-models/${modelId}/sensitivity?base_revision_id=${revisionId}`,
    isDcfSensitivity,
    0,
    open,
    staleRevisionMessage,
  );
  const identityError =
    data && (data.model_id !== modelId || data.revision_id !== revisionId)
      ? "The sensitivity response does not match the selected model revision. Reload the company."
      : undefined;
  return (
    <Card
      className="min-w-0 shadow-none"
      role="region"
      aria-label="DCF valuation sensitivity"
    >
      <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <CardTitle role="heading" aria-level={3} className="text-base">
            DCF valuation sensitivity
          </CardTitle>
          <Badge variant="outline">Hypothetical · read-only</Badge>
        </div>
        <Button
          variant="outline"
          className="min-h-11"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {open ? "Hide sensitivity" : "Explore sensitivity"}
        </Button>
      </CardHeader>
      {open && (
        <CardContent>
          {identityError || error === staleRevisionMessage ? (
            <div role="alert" className="space-y-3 text-sm">
              <p>{identityError ?? error}</p>
              <Button
                className="min-h-11"
                variant="outline"
                onClick={() => window.location.reload()}
              >
                Reload company
              </Button>
            </div>
          ) : data ? (
            <DcfSensitivityGrid data={data} />
          ) : (
            <PendingOrError error={error} retry={retry} />
          )}
        </CardContent>
      )}
    </Card>
  );
}
