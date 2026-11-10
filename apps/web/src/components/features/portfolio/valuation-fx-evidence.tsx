import { dateTime } from "@/lib/display";

/** Presents API-supplied conversion evidence without deriving financial values. */
export function ValuationFxEvidence({
  sourceCurrency,
  targetCurrency,
  rate,
  effectiveAt,
  syncStatus,
}: {
  sourceCurrency: string | null;
  targetCurrency: string;
  rate: string | null;
  effectiveAt: string | null;
  syncStatus?: string;
}) {
  if (!sourceCurrency) return <span>Source currency unavailable.</span>;
  if (sourceCurrency === targetCurrency)
    return <span>No currency conversion required.</span>;
  if (rate === null)
    return (
      <span>
        FX rate not recorded for this valuation ({sourceCurrency} →{" "}
        {targetCurrency}).
      </span>
    );
  return (
    <span className="block space-y-1">
      <span className="block tabular-nums">
        1 {sourceCurrency} = {rate} {targetCurrency}
      </span>
      <span className="block">
        {effectiveAt
          ? `FX effective ${dateTime(effectiveAt)}`
          : "FX effective time unavailable."}
      </span>
      {syncStatus === "NON_SYNCHRONOUS" && (
        <span className="block">
          FX effective and quote observation times differ.
        </span>
      )}
      {syncStatus === "TIMING_UNKNOWN" && (
        <span className="block">Quote observation timing is unavailable.</span>
      )}
    </span>
  );
}
