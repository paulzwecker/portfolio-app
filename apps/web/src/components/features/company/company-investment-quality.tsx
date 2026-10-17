"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PendingOrError } from "@/components/app/empty-state";
import { useResearch } from "@/hooks/use-research";
import {
  isScoreCurrents,
  isScoreHistory,
  scoreDimensions,
  type ScoreCurrent,
  type ScoreDimension,
  type ScoreStatus,
} from "@/lib/domain-contracts";
import { date } from "@/lib/display";

const scoreLabels: Record<ScoreDimension, string> = {
  DURABILITY_10Y: "10Y Durability",
  COMPOUNDER_QUALITY: "Compounder Quality",
  EXECUTION: "Execution",
  RISK: "Risk",
};

function displayScore(assessment: ScoreCurrent["assessment"]) {
  if (!assessment) return "Not assessed";
  if (assessment.status !== "ASSESSED") return assessment.status;
  return `${assessment.score} / 5`;
}

export function InvestmentQuality({ companyId }: { companyId: string }) {
  const current = useResearch(
    `companies/${encodeURIComponent(companyId)}/scores/current`,
    isScoreCurrents,
  );
  const history = useResearch(
    `companies/${encodeURIComponent(companyId)}/scores/history`,
    isScoreHistory,
  );
  return (
    <section
      id="investment-quality"
      aria-labelledby="investment-quality-title"
      className="mb-8 scroll-mt-5"
    >
      <div className="mb-3">
        <h2 id="investment-quality-title" className="text-xl font-semibold">
          Investment quality
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Four independent assessments. Risk rises with its score; it excludes
          valuation.
        </p>
      </div>
      {!current.data ? (
        <PendingOrError {...current} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {current.data.map((score) => {
            const earlier = history.data?.filter(
              (entry) =>
                entry.definition.id === score.definition.id &&
                entry.assessment.id !== score.assessment?.id,
            );
            return (
              <Card key={score.definition.id} className="min-w-0 shadow-none">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    {scoreLabels[score.definition.dimension]}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-2xl font-semibold tabular-nums">
                    {displayScore(score.assessment)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Scale {score.definition.minimum_score}–
                    {score.definition.maximum_score} {score.definition.units} ·{" "}
                    {score.definition.directionality === "HIGHER_IS_RISK"
                      ? "Higher means greater risk"
                      : "Higher is better"}
                  </p>
                  <p className="break-words text-xs leading-5">
                    {score.assessment?.rationale ??
                      "No assessment has been recorded for this dimension."}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Effective:{" "}
                    {score.assessment?.effective_at
                      ? date(score.assessment.effective_at)
                      : "Not recorded"}
                  </p>
                  {score.assessment && (
                    <Badge variant="secondary">{score.assessment.status}</Badge>
                  )}
                  <details className="border-t pt-3">
                    <summary className="cursor-pointer text-xs font-medium">
                      Score history (
                      {(earlier?.length ?? 0) + (score.assessment ? 1 : 0)})
                    </summary>
                    {history.error ? (
                      <div className="mt-3 space-y-2 text-xs">
                        <p role="alert">History is unavailable.</p>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={history.retry}
                        >
                          Retry history
                        </Button>
                      </div>
                    ) : !history.data ? (
                      <p className="mt-3 text-xs text-muted-foreground">
                        Loading history…
                      </p>
                    ) : history.data.filter(
                        (entry) =>
                          entry.definition.dimension ===
                          score.definition.dimension,
                      ).length === 0 ? (
                      <p className="mt-3 text-xs text-muted-foreground">
                        No historical assessments.
                      </p>
                    ) : (
                      <ol className="mt-3 space-y-3">
                        {history.data
                          .filter(
                            (entry) =>
                              entry.definition.dimension ===
                              score.definition.dimension,
                          )
                          .map((entry) => (
                            <li
                              key={entry.assessment.id}
                              className="border-l-2 pl-3 text-xs"
                            >
                              <p className="font-medium">
                                {entry.assessment.status === "ASSESSED"
                                  ? `${entry.assessment.score} / ${entry.definition.maximum_score}`
                                  : entry.assessment.status}
                              </p>
                              <p className="mt-1 text-muted-foreground">
                                Effective {date(entry.assessment.effective_at)}{" "}
                                · Recorded {date(entry.assessment.recorded_at)}{" "}
                                · {entry.assessment.actor}
                              </p>
                              <p className="mt-2 break-words leading-5">
                                {entry.assessment.rationale}
                              </p>
                              {entry.assessment.source && (
                                <p className="mt-1 break-words text-muted-foreground">
                                  Source: {entry.assessment.source}
                                </p>
                              )}
                              {entry.assessment.superseded_assessment_id && (
                                <p className="mt-1 break-all text-muted-foreground">
                                  Corrects assessment{" "}
                                  {entry.assessment.superseded_assessment_id}
                                </p>
                              )}
                            </li>
                          ))}
                      </ol>
                    )}
                  </details>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      {current.data && (
        <details className="mt-4 rounded-lg border bg-card p-4">
          <summary className="cursor-pointer text-sm font-medium">
            Record a new score assessment
          </summary>
          <ScoreEditor
            companyId={companyId}
            scores={current.data}
            changed={() => {
              current.retry();
              history.retry();
            }}
          />
        </details>
      )}
    </section>
  );
}

function ScoreEditor({
  companyId,
  scores,
  changed,
}: {
  companyId: string;
  scores: ScoreCurrent[];
  changed: () => void;
}) {
  const [dimension, setDimension] = useState<ScoreDimension>("DURABILITY_10Y");
  const [status, setStatus] = useState<ScoreStatus>("ASSESSED");
  const [score, setScore] = useState("");
  const [rationale, setRationale] = useState("");
  const [source, setSource] = useState("");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = scores.find(
    (item) => item.definition.dimension === dimension,
  );
  return (
    <Card className="mt-4 shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Record a new assessment</CardTitle>
        <p className="text-xs leading-5 text-muted-foreground">
          Saving creates an immutable history entry. Revisions link to the
          current assessment.
        </p>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!selected) return;
            setBusy(true);
            setError(null);
            try {
              const response = await fetch(
                `/api/research/companies/${encodeURIComponent(companyId)}/score-assessments`,
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  signal: AbortSignal.timeout(10000),
                  body: JSON.stringify({
                    dimension,
                    score: status === "ASSESSED" ? score : null,
                    status,
                    effective_at: effectiveAt
                      ? new Date(effectiveAt).toISOString()
                      : new Date().toISOString(),
                    rationale: rationale.trim(),
                    actor: "LOCAL_USER",
                    source: source.trim() || null,
                    superseded_assessment_id: selected.assessment?.id ?? null,
                  }),
                },
              );
              if (!response.ok)
                throw new Error(
                  response.status === 409
                    ? "A newer assessment exists. Reload scores before revising."
                    : "The assessment could not be saved. Check the score and try again.",
                );
              setScore("");
              setRationale("");
              setSource("");
              changed();
            } catch (failure) {
              setError(
                failure instanceof Error &&
                  failure.message.startsWith("A newer")
                  ? failure.message
                  : "The assessment could not be saved. Check the services and try again.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="block text-xs font-medium">
            Score dimension
            <select
              value={dimension}
              disabled={busy}
              onChange={(event) => {
                setDimension(event.target.value as ScoreDimension);
                setScore("");
              }}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            >
              {scoreDimensions.map((value) => (
                <option key={value} value={value}>
                  {scoreLabels[value]}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium">
            Data-quality state
            <select
              value={status}
              disabled={busy}
              onChange={(event) => {
                const next = event.target.value as ScoreStatus;
                setStatus(next);
                if (next !== "ASSESSED") setScore("");
              }}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            >
              {(["ASSESSED", "MISSING", "UNAVAILABLE", "INVALID"] as const).map(
                (value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="block text-xs font-medium">
            Score {status === "ASSESSED" ? "(required)" : "(leave blank)"}
            <input
              type="number"
              min={selected?.definition.minimum_score}
              max={selected?.definition.maximum_score}
              step="0.01"
              value={score}
              required={status === "ASSESSED"}
              disabled={busy || status !== "ASSESSED"}
              onChange={(event) => setScore(event.target.value)}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm tabular-nums"
            />
            <span className="mt-1 block font-normal text-muted-foreground">
              {selected?.definition.minimum_score}–
              {selected?.definition.maximum_score} ·
              {selected?.definition.directionality === "HIGHER_IS_RISK"
                ? " higher means greater risk"
                : " higher is better"}
            </span>
          </label>
          <label className="block text-xs font-medium">
            Effective at (blank uses now)
            <input
              type="datetime-local"
              value={effectiveAt}
              onChange={(event) => setEffectiveAt(event.target.value)}
              disabled={busy}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            />
          </label>
          <label className="block text-xs font-medium sm:col-span-2">
            Rationale
            <textarea
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              required
              maxLength={4000}
              rows={3}
              disabled={busy}
              className="mt-2 block w-full rounded-md border bg-card p-3 text-sm"
            />
          </label>
          <label className="block text-xs font-medium sm:col-span-2">
            Source URL or identifier (optional)
            <input
              value={source}
              onChange={(event) => setSource(event.target.value)}
              maxLength={1000}
              disabled={busy}
              className="mt-2 block h-10 w-full rounded-md border bg-card px-3 text-sm"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <Button disabled={busy || !rationale.trim()}>
              {busy ? "Saving…" : "Record score assessment"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Actor: Local user · Definition v{selected?.definition.version}
            </span>
          </div>
          {error && (
            <div
              role="alert"
              className="space-y-2 text-xs text-destructive sm:col-span-2"
            >
              <p>{error}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={changed}
              >
                Reload scores
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
