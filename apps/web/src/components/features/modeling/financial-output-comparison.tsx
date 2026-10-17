import { formatCurrency, percent } from "@/lib/display";
import type { FinancialModelCalculationOutputs } from "@/lib/domain-contracts";

export type ComparableFinancialOutputs = Pick<
  FinancialModelCalculationOutputs,
  | "bear_fv"
  | "base_fv"
  | "bull_fv"
  | "weighted_fv"
  | "weighted_upside"
  | "expected_cash_flow_irr"
  | "hurdle"
  | "expected_excess"
>;

const outputRows: Array<{
  field: keyof ComparableFinancialOutputs;
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

function display(value: string | null, ratio: boolean, currency: string) {
  return ratio
    ? percent(value)
    : formatCurrency(value, currency, 2, "Not supplied");
}

export function FinancialOutputComparison({
  output,
  currency,
  previous,
}: {
  output: ComparableFinancialOutputs;
  currency: string;
  previous?: ComparableFinancialOutputs | null;
}) {
  return (
    <dl className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {outputRows.map(({ field, label, ratio }) => {
        const before = previous?.[field] ?? null;
        const after = output[field];
        const changed =
          previous !== undefined && previous !== null && before !== after;
        return (
          <div key={field} className="min-w-0 rounded-md bg-secondary/40 p-3">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-1 break-words text-xs tabular-nums">
              {previous === undefined ? (
                <span className="font-semibold">
                  {display(after, !!ratio, currency)}
                </span>
              ) : (
                <>
                  <span className="text-muted-foreground">
                    {previous === null
                      ? "No accepted baseline"
                      : display(before, !!ratio, currency)}
                  </span>
                  <span
                    className="px-1.5 text-muted-foreground"
                    aria-hidden="true"
                  >
                    →
                  </span>
                  <span className="font-semibold">
                    {display(after, !!ratio, currency)}
                  </span>
                </>
              )}
            </dd>
            {previous !== undefined && previous !== null && (
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
