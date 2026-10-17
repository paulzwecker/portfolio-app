"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/app/status-indicator";
import {
  isCandidatePipelinePublicationResult,
  isCompanyCandidatePipeline,
  type CandidateGateOutcome,
  type CandidatePipelineQueueEntry,
  type CandidatePipelineRevisionCreate,
  type CompanyCandidatePipeline,
} from "@/lib/domain-contracts";
import { useResearch } from "@/hooks/use-research";
import { date } from "@/lib/display";

const gates = [
  ["DISCOVERY", "Discovery"],
  ["INITIAL_SCREEN", "Initial screen"],
  ["QUALITY_DURABILITY", "Quality / durability"],
  ["FUNDAMENTAL_COMPOUNDING", "Fundamental compounding"],
  ["DEEP_DIVE", "Deep dive"],
] as const;
const stages = [
  ["DISCOVERY", "Discovery"],
  ["INITIAL_SCREEN", "Initial screen"],
  ["QUALITY_DURABILITY", "Quality / durability"],
  ["FUNDAMENTAL_COMPOUNDING", "Fundamental compounding"],
  ["DEEP_DIVE", "Deep dive"],
  ["RESOLUTION", "Recommendation"],
] as const;
const outcomes: CandidateGateOutcome[] = [
  "NOT_ASSESSED",
  "INCOMPLETE",
  "PASS",
  "FAIL",
  "DATA_CHECK",
];

function readable(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "Unavailable";
}

export function CandidatePipelinePanel({
  candidates,
  loading,
  error,
  retry,
}: {
  candidates?: CandidatePipelineQueueEntry[];
  loading: boolean;
  error?: string;
  retry: () => void;
}) {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [recordedMessage, setRecordedMessage] = useState("");
  const visible = (candidates ?? []).filter((item) =>
    item.company.name.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const effectiveSelectedId = visible.some(
    (item) => item.company.id === selectedId,
  )
    ? selectedId
    : (visible[0]?.company.id ?? "");
  const detail = useResearch(
    effectiveSelectedId
      ? "companies/" +
          encodeURIComponent(effectiveSelectedId) +
          "/candidate-pipeline"
      : "",
    isCompanyCandidatePipeline,
    0,
    Boolean(effectiveSelectedId),
  );

  return (
    <section aria-labelledby="candidate-pipeline-heading" className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="candidate-pipeline-heading" className="text-lg font-semibold">
            Candidate Pipeline
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Discovery through deep dive. Gate outcomes are research records;
            they do not promote a company or change investment lifecycle.
          </p>
        </div>
        <label className="grid gap-1 text-xs font-medium sm:w-72">
          Find a Candidate
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="h-10 rounded-md border bg-background px-3 text-sm"
            placeholder="Company name"
          />
        </label>
      </div>
      {recordedMessage && (
        <p
          role="status"
          className="rounded-md border border-positive/30 bg-positive/5 p-3 text-sm"
        >
          {recordedMessage}
        </p>
      )}
      {error ? (
        <div className="rounded-md border border-destructive/40 p-4 text-sm">
          <p role="alert">{error}</p>
          <Button variant="outline" className="mt-3" onClick={retry}>
            Retry Candidate data
          </Button>
        </div>
      ) : loading ? (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          Loading Candidate research state…
        </p>
      ) : !visible.length ? (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          {candidates?.length
            ? "No Candidates match this search."
            : "No companies currently have the explicit Candidate lifecycle."}
        </p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(240px,0.72fr)_minmax(0,1.6fr)]">
          <div className="space-y-2" aria-label="Candidate companies">
            {visible.map((item) => (
              <button
                key={item.company.id}
                type="button"
                aria-pressed={effectiveSelectedId === item.company.id}
                onClick={() => setSelectedId(item.company.id)}
                className={
                  "w-full rounded-lg border p-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
                  (effectiveSelectedId === item.company.id
                    ? "border-primary bg-primary/5"
                    : "hover:bg-muted/50")
                }
              >
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{item.company.name}</span>
                  <StatusIndicator status={item.status} />
                </span>
                <span className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>{readable(item.stage)}</span>
                  <span>
                    Research Rank{" "}
                    {item.research_rank_position
                      ? "#" + item.research_rank_position
                      : readable(item.research_rank_status)}
                  </span>
                  {item.candidate_tier && (
                    <span>{item.candidate_tier} tier</span>
                  )}
                </span>
                {item.research_rank_reason && (
                  <span className="mt-2 block text-xs text-muted-foreground">
                    {item.research_rank_reason}
                  </span>
                )}
              </button>
            ))}
          </div>
          {effectiveSelectedId && (
            <CandidateDetail
              key={effectiveSelectedId}
              detail={detail.data}
              loading={!detail.data && !detail.error}
              error={detail.error}
              retry={detail.retry}
              onRecorded={(message) => {
                setRecordedMessage(message);
                detail.retry();
                retry();
              }}
            />
          )}
        </div>
      )}
    </section>
  );
}

function CandidateDetail({
  detail,
  loading,
  error,
  retry,
  onRecorded,
}: {
  detail?: CompanyCandidatePipeline;
  loading: boolean;
  error?: string;
  retry: () => void;
  onRecorded: (message: string) => void;
}) {
  const latest = detail?.history[0] ?? null;
  return (
    <div className="space-y-4">
      {loading && (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          Loading gates and revision history…
        </p>
      )}
      {error && (
        <div className="rounded-md border border-destructive/40 p-4 text-sm">
          <p role="alert">{error}</p>
          <Button variant="outline" className="mt-3" onClick={retry}>
            Retry Candidate detail
          </Button>
        </div>
      )}
      {detail && (
        <>
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle className="text-base">
                    {detail.company.name}
                  </CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Lifecycle {readable(detail.lifecycle)} · research status{" "}
                    {readable(detail.queue_entry.status)}
                  </p>
                </div>
                <Link
                  href={"/company/" + encodeURIComponent(detail.company.id)}
                  className="text-sm font-medium text-primary underline-offset-4 hover:underline"
                >
                  Open Company Explorer
                </Link>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {latest ? (
                <>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {latest.gates.map((gate) => (
                      <div
                        key={gate.id}
                        className="rounded-md border p-3 text-sm"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">
                            {readable(gate.gate)}
                          </span>
                          <StatusIndicator status={gate.outcome} />
                        </div>
                        {gate.rationale && (
                          <p className="mt-2 text-xs text-muted-foreground">
                            {gate.rationale}
                          </p>
                        )}
                        {(gate.evidence ?? []).length > 0 && (
                          <p className="mt-2 text-xs">
                            {(gate.evidence ?? []).length} linked evidence item
                            {(gate.evidence ?? []).length === 1 ? "" : "s"}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                  <div className="grid gap-3 border-t pt-3 text-sm sm:grid-cols-2">
                    <p>
                      <span className="text-muted-foreground">
                        Current stage
                      </span>
                      <br />
                      {readable(latest.stage)} · revision{" "}
                      {latest.revision_number}
                    </p>
                    <p>
                      <span className="text-muted-foreground">Next action</span>
                      <br />
                      {latest.next_action ?? "No next action recorded"}
                    </p>
                    <p className="sm:col-span-2">
                      <span className="text-muted-foreground">
                        Unresolved questions
                      </span>
                      <br />
                      {latest.unresolved_questions.length
                        ? latest.unresolved_questions.join(" · ")
                        : "None recorded"}
                    </p>
                  </div>
                  <details className="rounded-md border p-3 text-sm">
                    <summary className="cursor-pointer font-medium">
                      Revision history · {detail.history.length}
                    </summary>
                    <ol className="mt-3 space-y-3">
                      {detail.history.map((revision) => (
                        <li key={revision.id} className="border-l-2 pl-3">
                          <p className="font-medium">
                            Revision {revision.revision_number} ·{" "}
                            {readable(revision.stage)}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            Effective {date(revision.effective_at)} · recorded{" "}
                            {date(revision.recorded_at)} · {revision.author_id}
                          </p>
                          <p className="mt-1 text-xs">{revision.rationale}</p>
                        </li>
                      ))}
                    </ol>
                  </details>
                </>
              ) : (
                <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                  No prior Candidate pipeline history exists.
                </p>
              )}
            </CardContent>
          </Card>
          <CandidateRevisionForm
            key={(latest?.id ?? "new") + ":" + detail.history.length}
            detail={detail}
            onRecorded={onRecorded}
          />
        </>
      )}
    </div>
  );
}

function CandidateRevisionForm({
  detail,
  onRecorded,
}: {
  detail: CompanyCandidatePipeline;
  onRecorded: (message: string) => void;
}) {
  const latest = detail.history[0] ?? null;
  const [stage, setStage] = useState<(typeof stages)[number][0]>(
    latest?.stage ?? "DISCOVERY",
  );
  const [outcomeByGate, setOutcomeByGate] = useState<
    Record<string, CandidateGateOutcome>
  >(() =>
    Object.fromEntries(
      gates.map(([key]) => [
        key,
        latest?.gates.find((gate) => gate.gate === key)?.outcome ??
          "NOT_ASSESSED",
      ]),
    ),
  );
  const [rationaleByGate, setRationaleByGate] = useState<
    Record<string, string>
  >(() =>
    Object.fromEntries(
      gates.map(([key]) => [
        key,
        latest?.gates.find((gate) => gate.gate === key)?.rationale ?? "",
      ]),
    ),
  );
  const [evidenceByGate, setEvidenceByGate] = useState<Record<string, string>>(
    () => Object.fromEntries(gates.map(([key]) => [key, ""])),
  );
  const [perShareConfirmed, setPerShareConfirmed] = useState(
    latest?.gates.find((gate) => gate.gate === "FUNDAMENTAL_COMPOUNDING")
      ?.normalized_per_share_basis_confirmed ?? false,
  );
  const [rationale, setRationale] = useState("");
  const [author, setAuthor] = useState("local-analyst");
  const [nextAction, setNextAction] = useState(latest?.next_action ?? "");
  const [questions, setQuestions] = useState(
    latest?.unresolved_questions.join("\n") ?? "",
  );
  const [disposition, setDisposition] = useState<
    "WATCHLIST" | "INCUBATE" | "DROP" | ""
  >(latest?.disposition ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setMessage("");
    const payload: CandidatePipelineRevisionCreate = {
      actor: "LOCAL_USER",
      author_id: author.trim(),
      disposition: disposition || null,
      effective_at: new Date().toISOString(),
      expected_revision_id: latest?.id ?? null,
      gates: gates.map(([gate]) => {
        const selected = detail.evidence_options.find(
          (option) => option.reference_id === evidenceByGate[gate],
        );
        return {
          gate,
          outcome: outcomeByGate[gate],
          rationale: rationaleByGate[gate].trim() || null,
          normalized_per_share_basis_confirmed:
            gate === "FUNDAMENTAL_COMPOUNDING" && perShareConfirmed,
          evidence: selected
            ? [
                {
                  evidence_type: selected.evidence_type,
                  reference_id: selected.reference_id,
                  relationship: "CONTEXT",
                },
              ]
            : [],
        };
      }),
      next_action: nextAction.trim() || null,
      rationale: rationale.trim(),
      source: "web-research-workspace",
      submission_id: crypto.randomUUID(),
      unresolved_questions: questions
        .split("\n")
        .map((value) => value.trim())
        .filter(Boolean),
      stage,
    };
    try {
      const response = await fetch(
        "/api/research/companies/" +
          encodeURIComponent(detail.company.id) +
          "/candidate-pipeline-revisions",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      const result: unknown = await response.json();
      if (!response.ok || !isCandidatePipelinePublicationResult(result)) {
        const issue =
          typeof result === "object" && result !== null && "detail" in result
            ? String(result.detail)
            : "The Candidate revision could not be recorded.";
        throw new Error(issue);
      }
      const successMessage =
        "Research revision " +
        result.revision.revision_number +
        " recorded. Lifecycle and portfolio state are unchanged.";
      setMessage(successMessage);
      setRationale("");
      onRecorded(successMessage);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The Candidate revision could not be recorded.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Record a research revision</CardTitle>
        <p className="text-sm text-muted-foreground">
          Each submission appends a full gate snapshot against the current
          revision. The API validates stage progression and evidence.
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void submit(event)} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-xs font-medium">
              Research stage
              <select
                value={stage}
                onChange={(event) =>
                  setStage(event.target.value as (typeof stages)[number][0])
                }
                className="h-10 rounded-md border bg-background px-3 text-sm"
              >
                {stages.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-xs font-medium">
              Research recommendation
              <select
                value={disposition}
                onChange={(event) =>
                  setDisposition(
                    event.target.value as
                      "WATCHLIST" | "INCUBATE" | "DROP" | "",
                  )
                }
                className="h-10 rounded-md border bg-background px-3 text-sm"
              >
                <option value="">No recommendation</option>
                <option value="WATCHLIST">Watchlist</option>
                <option value="INCUBATE">Incubate</option>
                <option value="DROP">Drop</option>
              </select>
            </label>
            <label className="grid gap-1 text-xs font-medium">
              Author identity
              <input
                required
                value={author}
                onChange={(event) => setAuthor(event.target.value)}
                className="h-10 rounded-md border bg-background px-3 text-sm"
              />
            </label>
            <label className="grid gap-1 text-xs font-medium">
              Next action
              <input
                value={nextAction}
                onChange={(event) => setNextAction(event.target.value)}
                className="h-10 rounded-md border bg-background px-3 text-sm"
              />
            </label>
          </div>
          <div className="grid gap-3">
            {gates.map(([gate, label]) => (
              <fieldset
                key={gate}
                className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2"
              >
                <legend className="px-1 text-sm font-medium">{label}</legend>
                <label className="grid gap-1 text-xs font-medium">
                  Gate outcome
                  <select
                    value={outcomeByGate[gate]}
                    onChange={(event) =>
                      setOutcomeByGate((current) => ({
                        ...current,
                        [gate]: event.target.value as CandidateGateOutcome,
                      }))
                    }
                    className="h-10 rounded-md border bg-background px-3 text-sm"
                  >
                    {outcomes.map((value) => (
                      <option key={value} value={value}>
                        {readable(value)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-xs font-medium">
                  Evidence source
                  <select
                    value={evidenceByGate[gate]}
                    onChange={(event) =>
                      setEvidenceByGate((current) => ({
                        ...current,
                        [gate]: event.target.value,
                      }))
                    }
                    className="h-10 rounded-md border bg-background px-3 text-sm"
                  >
                    <option value="">No linked evidence</option>
                    {detail.evidence_options.map((option) => (
                      <option
                        key={option.reference_id}
                        value={option.reference_id}
                      >
                        {option.label} · {readable(option.availability_status)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-xs font-medium sm:col-span-2">
                  Gate rationale
                  <input
                    value={rationaleByGate[gate]}
                    onChange={(event) =>
                      setRationaleByGate((current) => ({
                        ...current,
                        [gate]: event.target.value,
                      }))
                    }
                    className="h-10 rounded-md border bg-background px-3 text-sm"
                  />
                </label>
                {gate === "FUNDAMENTAL_COMPOUNDING" && (
                  <label className="flex items-start gap-2 text-xs sm:col-span-2">
                    <input
                      type="checkbox"
                      checked={perShareConfirmed}
                      onChange={(event) =>
                        setPerShareConfirmed(event.target.checked)
                      }
                      className="mt-0.5 size-4"
                    />
                    I reviewed the linked output as normalized per-share
                    fundamental compounding.
                  </label>
                )}
              </fieldset>
            ))}
          </div>
          <label className="grid gap-1 text-xs font-medium">
            Revision rationale
            <textarea
              required
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              className="min-h-20 rounded-md border bg-background px-3 py-2 text-sm"
            />
          </label>
          <label className="grid gap-1 text-xs font-medium">
            Unresolved questions · one per line
            <textarea
              value={questions}
              onChange={(event) => setQuestions(event.target.value)}
              className="min-h-16 rounded-md border bg-background px-3 py-2 text-sm"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="submit"
              disabled={pending || !author.trim() || !rationale.trim()}
            >
              {pending ? "Recording…" : "Record research revision"}
            </Button>
            {latest && (
              <span className="text-xs text-muted-foreground">
                Base revision {latest.revision_number} · recorded{" "}
                {date(latest.recorded_at)}
              </span>
            )}
          </div>
          {message && (
            <p
              role="status"
              className="rounded-md border border-positive/30 bg-positive/5 p-3 text-sm"
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
        </form>
      </CardContent>
    </Card>
  );
}
