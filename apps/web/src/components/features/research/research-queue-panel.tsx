"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusIndicator } from "@/components/app/status-indicator";
import { SourceReference } from "@/components/app/source-reference";
import {
  isGoogleSheetsThesisWatchPublish,
  isResearchQueueCompletionResult,
  isResearchQueueHistory,
  isResearchTriggerRefreshResult,
  type ResearchQueue,
  type ResearchQueueCompletion,
  type ResearchQueueTask,
  type ResearchTriggerReadResult,
} from "@/lib/domain-contracts";
import { useResearch } from "@/hooks/use-research";
import { date } from "@/lib/display";

type WorkGroup = "ALL" | "CANDIDATE" | "THESIS_EVIDENCE" | "MODEL" | "RISK";
const groups: [WorkGroup, string][] = [
  ["ALL", "All work"],
  ["CANDIDATE", "Candidate pipeline"],
  ["THESIS_EVIDENCE", "Thesis & evidence"],
  ["MODEL", "Model review"],
  ["RISK", "Risk & Watchlist"],
];

function groupFor(task: ResearchQueueTask): Exclude<WorkGroup, "ALL"> {
  if (task.task_type === "CANDIDATE_STAGE") return "CANDIDATE";
  if (
    [
      "THESIS_REVIEW",
      "THESIS_QUESTION",
      "MATERIAL_EVIDENCE",
      "RESEARCH_TRIGGER",
    ].includes(task.task_type)
  )
    return "THESIS_EVIDENCE";
  if (["MODEL_REUNDERWRITE", "MODEL_INTEGRITY"].includes(task.task_type))
    return "MODEL";
  return "RISK";
}

function readable(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "Unavailable";
}

export function ResearchQueuePanel({
  queue,
  loading,
  error,
  retry,
  triggers,
  triggerLoading,
  triggerError,
  retryTriggers,
}: {
  queue?: ResearchQueue;
  loading: boolean;
  error?: string;
  retry: () => void;
  triggers?: ResearchTriggerReadResult;
  triggerLoading: boolean;
  triggerError?: string;
  retryTriggers: () => void;
}) {
  const [group, setGroup] = useState<WorkGroup>("ALL");
  const [lifecycle, setLifecycle] = useState("");
  const [search, setSearch] = useState("");
  const [expandedTaskId, setExpandedTaskId] = useState("");
  const [scanMessage, setScanMessage] = useState("");
  const [scanError, setScanError] = useState("");
  const [scanPending, setScanPending] = useState(false);
  const history = useResearch(
    "research-queue/history?limit=100",
    isResearchQueueHistory,
  );
  const tasks = useMemo(
    () =>
      (queue?.tasks ?? []).filter((task) => {
        if (group !== "ALL" && groupFor(task) !== group) return false;
        if (lifecycle && task.company.lifecycle !== lifecycle) return false;
        return (
          !search.trim() ||
          (task.company.name + " " + task.title + " " + task.reason)
            .toLowerCase()
            .includes(search.trim().toLowerCase())
        );
      }),
    [queue?.tasks, group, lifecycle, search],
  );

  return (
    <section aria-labelledby="research-queue-heading" className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 id="research-queue-heading" className="text-lg font-semibold">
            Research Review Queue
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Canonical work conditions, source context, and analyst completion.
            Completing a review does not accept a proposal or alter investment
            state.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={triggerLoading || scanPending}
            onClick={() => {
              setScanPending(true);
              setScanMessage("");
              setScanError("");
              void runTriggerScan()
                .then((result) => {
                  setScanMessage(
                    result.created +
                      " new triggers captured; " +
                      result.replayed +
                      " exact replays skipped.",
                  );
                  retryTriggers();
                  retry();
                })
                .catch((failure: unknown) => {
                  setScanError(
                    failure instanceof Error
                      ? failure.message
                      : "Research triggers could not be refreshed.",
                  );
                })
                .finally(() => setScanPending(false));
            }}
          >
            {triggerLoading || scanPending
              ? "Scanning…"
              : "Scan for new triggers"}
          </Button>
          <PublishTriggerPage />
        </div>
      </div>

      {scanMessage && (
        <p role="status" className="rounded-md border p-3 text-sm">
          {scanMessage}
        </p>
      )}
      {scanError && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 p-3 text-sm"
        >
          {scanError}
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <QueueSummary label="Open work" value={queue?.counts.open} />
        <QueueSummary label="Completed" value={queue?.counts.complete} />
        <QueueSummary
          label="Open evidence triggers"
          value={
            triggers?.triggers.filter(
              (trigger) => trigger.processing_state === "OPEN",
            ).length
          }
        />
      </div>

      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_190px_220px]">
        <label className="grid gap-1 text-xs font-medium">
          Search work and companies
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="h-10 rounded-md border bg-background px-3 text-sm"
            placeholder="Company, task, source reason"
          />
        </label>
        <label className="grid gap-1 text-xs font-medium">
          Lifecycle
          <select
            value={lifecycle}
            onChange={(event) => setLifecycle(event.target.value)}
            className="h-10 rounded-md border bg-background px-3 text-sm"
          >
            <option value="">All lifecycle states</option>
            <option value="PORTFOLIO">Portfolio</option>
            <option value="WATCHLIST">Watchlist</option>
            <option value="CANDIDATE">Candidate</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium">
          Work type
          <select
            value={group}
            onChange={(event) => setGroup(event.target.value as WorkGroup)}
            className="h-10 rounded-md border bg-background px-3 text-sm"
          >
            {groups.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 p-4 text-sm">
          <p role="alert">{error}</p>
          <Button variant="outline" className="mt-3" onClick={retry}>
            Retry queue
          </Button>
        </div>
      ) : loading ? (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          Loading research work…
        </p>
      ) : tasks.length === 0 ? (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          No current queue items match these filters. This is not a rating or a
          claim that research is complete.
        </p>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <QueueTaskCard
              key={task.task_id}
              task={task}
              expanded={expandedTaskId === task.task_id}
              onExpand={() =>
                setExpandedTaskId((current) =>
                  current === task.task_id ? "" : task.task_id,
                )
              }
              onComplete={() => {
                retry();
                history.retry();
              }}
            />
          ))}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <section aria-labelledby="trigger-history-heading">
          <h3
            id="trigger-history-heading"
            className="mb-2 text-sm font-semibold"
          >
            Evidence triggers
          </h3>
          {triggerError ? (
            <p
              role="alert"
              className="rounded-md border border-destructive/40 p-3 text-sm"
            >
              Trigger history unavailable. {triggerError}
            </p>
          ) : triggerLoading ? (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              Loading source triggers…
            </p>
          ) : !triggers?.triggers.length ? (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              No captured triggers. The source detector does not infer thesis
              significance.
            </p>
          ) : (
            <ul className="space-y-2">
              {triggers.triggers.slice(0, 12).map((trigger) => (
                <li key={trigger.id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Link
                      href={
                        "/company/" + encodeURIComponent(trigger.company.id)
                      }
                      className="font-medium hover:text-primary"
                    >
                      {trigger.company.name}
                    </Link>
                    <StatusIndicator status={trigger.processing_state} />
                  </div>
                  <p className="mt-1 text-sm">{trigger.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {trigger.reason} · source recorded{" "}
                    {date(trigger.source_recorded_at)}
                  </p>
                  {trigger.source_reference && (
                    <SourceReference
                      href={trigger.source_reference}
                      label="Open source"
                      className="mt-2 inline-flex"
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
        <CompletedReviewHistory
          history={history.data}
          error={history.error}
          retry={history.retry}
        />
      </div>
    </section>
  );
}

function QueueSummary({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">
        {value === undefined ? "Unavailable" : value}
      </p>
    </div>
  );
}

function QueueTaskCard({
  task,
  expanded,
  onExpand,
  onComplete,
}: {
  task: ResearchQueueTask;
  expanded: boolean;
  onExpand: () => void;
  onComplete: () => void;
}) {
  return (
    <article className="rounded-lg border bg-card p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={"/company/" + encodeURIComponent(task.company.id)}
              className="font-semibold hover:text-primary"
            >
              {task.company.name}
            </Link>
            <Badge variant="secondary">
              {readable(task.company.lifecycle)}
            </Badge>
            <StatusIndicator status={task.status} />
          </div>
          <h3 className="mt-2 text-sm font-medium">{task.title}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{task.reason}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            {readable(task.task_type)} · {readable(task.owner_workflow)}
            {task.due_at ? " · due " + date(task.due_at) : ""}
            {task.research_rank_position
              ? " · Research Rank #" + task.research_rank_position
              : ""}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {task.judgment_required
              ? "Analyst judgment required"
              : "Deterministic review condition"}
            {" · "}
            {task.source_recorded_at
              ? "source recorded " + date(task.source_recorded_at)
              : "source time unavailable"}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button type="button" variant="outline" onClick={onExpand}>
            {expanded ? "Close review" : "Complete review"}
          </Button>
          <Link
            href={
              task.company.lifecycle === "CANDIDATE"
                ? "/research?view=pipeline"
                : "/company/" + encodeURIComponent(task.company.id)
            }
            className="inline-flex min-h-9 items-center rounded-md px-2 text-sm text-primary underline-offset-4 hover:underline"
          >
            {task.company.lifecycle === "CANDIDATE"
              ? "Open pipeline"
              : "Company"}
          </Link>
        </div>
      </div>
      {expanded && task.status === "OPEN" && (
        <ReviewCompletionForm task={task} onComplete={onComplete} />
      )}
      {expanded && task.status === "COMPLETE" && (
        <p className="mt-3 rounded-md bg-muted p-3 text-sm">
          Completed by {task.completed_by ?? "reviewer"} on{" "}
          {task.completed_at ? date(task.completed_at) : "date unavailable"}.
          {task.completion_note ? " " + task.completion_note : ""}
        </p>
      )}
      {task.sources.length > 0 && (
        <details className="mt-3 rounded-md border p-3 text-sm">
          <summary className="cursor-pointer font-medium">
            Sources and trigger rule · {task.sources.length}
          </summary>
          <p className="mt-2 text-xs text-muted-foreground">
            {task.trigger_rule}
          </p>
          <ul className="mt-2 space-y-2">
            {task.sources.map((source) => (
              <li
                key={source.source_record_id}
                className="flex flex-wrap items-center justify-between gap-2 text-xs"
              >
                <span>
                  {source.title} · {readable(source.source_type)}
                </span>
                <span className="text-muted-foreground">
                  {source.published_at
                    ? "published " + date(source.published_at)
                    : source.recorded_at
                      ? "recorded " + date(source.recorded_at)
                      : "source time unknown"}
                </span>
                {source.source_url && (
                  <SourceReference href={source.source_url} label="Source" />
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

function ReviewCompletionForm({
  task,
  onComplete,
}: {
  task: ResearchQueueTask;
  onComplete: () => void;
}) {
  const [actor, setActor] = useState("Local analyst");
  const [note, setNote] = useState("");
  const [classification, setClassification] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setSuccess("");
    try {
      const response = await fetch(
        "/api/research/research-queue/" +
          encodeURIComponent(task.task_id) +
          "/complete",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            condition_fingerprint: task.condition_fingerprint,
            completed_by: actor.trim(),
            completion_note: note.trim(),
            trigger_classification: classification || null,
          }),
        },
      );
      const payload: unknown = await response.json();
      if (!response.ok || !isResearchQueueCompletionResult(payload)) {
        const detail =
          typeof payload === "object" && payload !== null && "detail" in payload
            ? String(payload.detail)
            : "The review completion was not recorded.";
        throw new Error(detail);
      }
      setSuccess("Review recorded. Canonical investment state is unchanged.");
      onComplete();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The review completion was not recorded.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void submit(event)}
      className="mt-4 grid gap-3 border-t pt-4 md:grid-cols-2"
    >
      <label className="grid gap-1 text-xs font-medium">
        Reviewer
        <input
          required
          value={actor}
          onChange={(event) => setActor(event.target.value)}
          className="h-10 rounded-md border bg-background px-3 text-sm"
        />
      </label>
      {task.task_type === "RESEARCH_TRIGGER" ? (
        <label className="grid gap-1 text-xs font-medium">
          Thesis Watch classification
          <select
            value={classification}
            onChange={(event) => setClassification(event.target.value)}
            className="h-10 rounded-md border bg-background px-3 text-sm"
          >
            <option value="">Not classified</option>
            <option value="NOISE">Noise</option>
            <option value="INCREMENTAL">Incremental</option>
            <option value="MAJOR_STRUCTURAL">Major structural</option>
          </select>
        </label>
      ) : (
        <div className="text-xs text-muted-foreground">
          This records completion of the review condition only.
        </div>
      )}
      <label className="grid gap-1 text-xs font-medium md:col-span-2">
        Review note
        <textarea
          required
          value={note}
          onChange={(event) => setNote(event.target.value)}
          className="min-h-16 rounded-md border bg-background px-3 py-2 text-sm"
          placeholder="What was reviewed, and what remains unresolved?"
        />
      </label>
      <div className="md:col-span-2">
        <Button
          type="submit"
          disabled={pending || !actor.trim() || !note.trim()}
        >
          {pending ? "Recording…" : "Record review complete"}
        </Button>
      </div>
      {success && (
        <p role="status" className="md:col-span-2 text-sm">
          {success}
        </p>
      )}
      {error && (
        <p role="alert" className="md:col-span-2 text-sm text-destructive">
          {error}
        </p>
      )}
    </form>
  );
}

function CompletedReviewHistory({
  history,
  error,
  retry,
}: {
  history?: ResearchQueueCompletion[];
  error?: string;
  retry: () => void;
}) {
  return (
    <section aria-labelledby="completed-review-heading">
      <h3 id="completed-review-heading" className="mb-2 text-sm font-semibold">
        Recent completed reviews
      </h3>
      {error ? (
        <div className="rounded-md border border-destructive/40 p-3 text-sm">
          <p role="alert">Completion history is unavailable.</p>
          <Button variant="outline" className="mt-2" onClick={retry}>
            Retry history
          </Button>
        </div>
      ) : !history ? (
        <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          Loading completion history…
        </p>
      ) : history.length === 0 ? (
        <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          No queue completion records yet.
        </p>
      ) : (
        <ol className="space-y-2">
          {history.slice(0, 10).map((entry) => (
            <li key={entry.id} className="rounded-md border p-3">
              <Link
                href={"/company/" + encodeURIComponent(entry.task.company.id)}
                className="font-medium hover:text-primary"
              >
                {entry.task.company.name}
              </Link>
              <p className="mt-1 text-xs text-muted-foreground">
                {entry.task.title} · {entry.completed_by} ·{" "}
                {date(entry.completed_at)}
              </p>
              {entry.completion_note && (
                <p className="mt-2 text-sm">{entry.completion_note}</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

async function runTriggerScan() {
  const response = await fetch(
    "/api/research/research-triggers/refresh?lookback_days=30",
    { method: "POST", cache: "no-store" },
  );
  const result: unknown = await response.json();
  if (!response.ok || !isResearchTriggerRefreshResult(result)) {
    const detail =
      typeof result === "object" && result !== null && "detail" in result
        ? String(result.detail)
        : "Research triggers could not be refreshed.";
    throw new Error(detail);
  }
  return result;
}

function PublishTriggerPage() {
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function publish() {
    setPending(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(
        "/api/research/google-sheets-sync/thesis-watch/publish",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ limit: 50, offset: 0 }),
        },
      );
      const result: unknown = await response.json();
      if (!response.ok || !isGoogleSheetsThesisWatchPublish(result)) {
        const detail =
          typeof result === "object" && result !== null && "detail" in result
            ? String(result.detail)
            : "Trigger context could not be published.";
        throw new Error(detail);
      }
      setMessage(result.message);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Trigger context could not be published.",
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="grid gap-1">
      <Button
        variant="outline"
        disabled={pending}
        onClick={() => void publish()}
      >
        {pending ? "Publishing…" : "Publish trigger page to Sheets"}
      </Button>
      {message && (
        <span role="status" className="text-xs text-muted-foreground">
          {message}
        </span>
      )}
      {error && (
        <span role="alert" className="text-xs text-destructive">
          {error}
        </span>
      )}
    </div>
  );
}
