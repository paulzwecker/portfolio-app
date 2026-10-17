import { Button } from "@/components/ui/button";

export function FinancialPeriodControls({
  periodType,
  onPeriodType,
  range,
  onRange,
  cutoff,
  onCutoff,
}: {
  periodType: "ANNUAL" | "QUARTERLY";
  onPeriodType: (value: "ANNUAL" | "QUARTERLY") => void;
  range: number;
  onRange: (value: number) => void;
  cutoff: string;
  onCutoff: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div
        className="flex gap-1"
        role="group"
        aria-label="Financial period type"
      >
        {(["ANNUAL", "QUARTERLY"] as const).map((value) => (
          <Button
            key={value}
            size="sm"
            variant={value === periodType ? "default" : "outline"}
            aria-pressed={value === periodType}
            onClick={() => onPeriodType(value)}
          >
            {value === "ANNUAL" ? "Annual" : "Quarterly"}
          </Button>
        ))}
      </div>
      <label className="text-xs font-medium">
        History
        <select
          aria-label="Financial history range"
          value={range}
          onChange={(event) => onRange(Number(event.target.value))}
          className="ml-2 h-9 rounded-md border bg-card px-2 text-sm"
        >
          {(periodType === "ANNUAL" ? [5, 10, 20, 40] : [8, 16, 24, 40]).map(
            (n) => (
              <option key={n} value={n}>
                {n} {periodType === "ANNUAL" ? "years" : "quarters"}
              </option>
            ),
          )}
        </select>
      </label>
      <label className="text-xs font-medium">
        App knowledge cutoff
        <input
          type="date"
          aria-label="App knowledge cutoff"
          value={cutoff}
          onChange={(event) => onCutoff(event.target.value)}
          className="ml-2 h-9 max-w-full rounded-md border bg-card px-2 text-sm"
        />
      </label>
      {cutoff && (
        <Button size="sm" variant="ghost" onClick={() => onCutoff("")}>
          Latest known
        </Button>
      )}
    </div>
  );
}
