"use client";

import { useState } from "react";
import { isGainHistory, type GainHistory } from "@/lib/domain-contracts";
import { ChartContainer } from "@/components/app/chart-container";
import { EmptyState, PendingOrError } from "@/components/app/empty-state";
import { useResearch } from "@/hooks/use-research";

const euros = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
});

function GainChart({ history }: { history: GainHistory }) {
  const points = history.points;
  const [selected, setSelected] = useState<number | null>(null);
  const index = Math.min(selected ?? points.length - 1, points.length - 1);
  const point = points[index];
  const amounts = points.flatMap((p) =>
    p.gain === null ? [] : [Number(p.gain)],
  );
  const low = Math.min(0, ...amounts);
  const high = Math.max(0, ...amounts);
  const x = (i: number) => (1000 * i) / Math.max(1, points.length - 1);
  const y = (v: number) => 185 - (180 * (v - low)) / (high - low || 1);
  const line = points
    .map((p, i) => {
      if (p.gain === null) return "";
      const command = i === 0 || points[i - 1].gain === null ? "M" : "L";
      return command + x(i).toFixed(2) + "," + y(Number(p.gain)).toFixed(2);
    })
    .join(" ");
  return (
    <ChartContainer
      title="Cumulative security gain / loss"
      description={`${history.open_positions} current and ${history.closed_positions} exited positions · EUR, including recorded net dividends and trade costs.`}
    >
      <p className="text-xl font-semibold tabular-nums">
        {point.gain === null
          ? "Mark unavailable"
          : euros.format(Number(point.gain))}
      </p>
      <p className="text-xs text-muted-foreground">{point.day}</p>
      <div className="mt-3 flex gap-2">
        <div className="flex flex-col justify-between py-1 text-xs text-muted-foreground">
          <span>{euros.format(high)}</span>
          <span>{euros.format(low)}</span>
        </div>
        <svg
          viewBox="0 0 1000 190"
          preserveAspectRatio="none"
          className="h-48 min-w-0 flex-1 touch-pan-y"
          role="img"
          aria-label="Daily cumulative security gain and loss in euros"
          onPointerMove={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            setSelected(
              Math.round(
                Math.min(
                  1,
                  Math.max(0, (event.clientX - rect.left) / rect.width),
                ) *
                  (points.length - 1),
              ),
            );
          }}
        >
          <line
            x1="0"
            x2="1000"
            y1={y(0)}
            y2={y(0)}
            stroke="currentColor"
            opacity=".3"
          />
          <path
            d={line}
            fill="none"
            stroke="currentColor"
            className="text-primary"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1={x(index)}
            x2={x(index)}
            y1="0"
            y2="190"
            stroke="currentColor"
            strokeDasharray="3 4"
            opacity=".55"
          />
        </svg>
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted-foreground">
        <span>{points[0].day}</span>
        <span>{points[points.length - 1].day}</span>
      </div>
      <input
        className="w-full"
        type="range"
        aria-label="Inspect a performance date"
        aria-valuetext={point.day}
        min="0"
        max={points.length - 1}
        value={index}
        onChange={(event) => setSelected(Number(event.target.value))}
      />
      <div className="mt-3 space-y-1 text-xs text-muted-foreground">
        {history.provisional.length > 0 && (
          <p>
            Provisional · dividend review open for{" "}
            {history.provisional.join(", ")}.
          </p>
        )}
        <p>
          Excludes cash balances, interest and account transfers
          {history.excluded.length
            ? `, plus ${history.excluded.join(", ")}`
            : ""}
          . Reference closes and FX carry forward for up to seven calendar days.
          Gaps indicate unavailable marks.
        </p>
      </div>
    </ChartContainer>
  );
}

export function PortfolioPerformanceSection({ id }: { id: string }) {
  const state = useResearch(`portfolios/${id}/gain-history`, isGainHistory);
  return (
    <section id="portfolio-performance">
      {state.data === undefined ? (
        <PendingOrError error={state.error} retry={state.retry} />
      ) : state.data?.portfolio_id === id ? (
        <GainChart history={state.data} />
      ) : (
        <EmptyState
          title="Historical portfolio performance is unavailable"
          description="A reconciled securities history has yet to be published for this portfolio."
        />
      )}
    </section>
  );
}
