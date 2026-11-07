import { StatusIndicator } from "@/components/app/status-indicator";
import type { OperationalJobRequest } from "@/lib/domain-contracts";
import { dateTime, statusLabel } from "@/lib/display";

export function JobStatus({
  job,
  compact = false,
  manualRunnerEnabled = false,
}: {
  job: OperationalJobRequest;
  compact?: boolean;
  manualRunnerEnabled?: boolean;
}) {
  const active = job.status === "QUEUED" || job.status === "RUNNING";
  return (
    <div
      role="status"
      aria-live="polite"
      className="min-w-0 space-y-2 rounded-md border bg-card p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusIndicator status={job.status} />
        {active && job.next_attempt_at && (
          <span className="text-xs text-muted-foreground">
            Retry after {dateTime(job.next_attempt_at)}
          </span>
        )}
      </div>
      <p className="break-words text-sm font-medium">
        {job.company_name ?? statusLabel(job.job_name)}
        <span className="font-normal text-muted-foreground">
          {job.scope_kind === "COMPANY"
            ? ` · ${statusLabel(job.job_name)} · ${job.lifecycle ? statusLabel(job.lifecycle) : "Lifecycle unassigned"}`
            : " · Active universe"}
        </span>
      </p>
      <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Requested</dt>
          <dd>{dateTime(job.requested_at)}</dd>
        </div>
        {job.finished_at && (
          <div>
            <dt className="text-muted-foreground">Finished</dt>
            <dd>{dateTime(job.finished_at)}</dd>
          </div>
        )}
      </dl>
      {job.attempts.length > 0 && (
        <ol className="space-y-1 border-l pl-3 text-xs">
          {job.attempts.slice(-4).map((attempt) => (
            <li
              key={attempt.id}
              className="flex flex-wrap items-center justify-between gap-2"
            >
              <span>{statusLabel(attempt.step_name)}</span>
              <StatusIndicator status={attempt.status} />
            </li>
          ))}
        </ol>
      )}
      {job.job_name === "WORKBOOK_SYNC" && job.attempts.length > 0 && (
        <details className="rounded-md border bg-muted/30 p-2 text-xs">
          <summary className="cursor-pointer font-medium">
            Frozen workbook and preview details
          </summary>
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words">
            {JSON.stringify(
              job.attempts
                .filter((attempt) => attempt.step_name === "WORKBOOK_SYNC")
                .map((attempt) => attempt.result),
              null,
              2,
            )}
          </pre>
          <p className="mt-2 text-muted-foreground">
            This request stages and previews a frozen source only. It never
            applies workbook changes.
          </p>
        </details>
      )}
      {(job.error_message || job.error_code) && (
        <p className="break-words text-xs text-warning">
          {job.error_message ?? statusLabel(job.error_code)}
        </p>
      )}
      {!compact && job.attempts.length === 0 && active && (
        <p className="text-xs text-muted-foreground">
          {manualRunnerEnabled
            ? "Queued for an operator-run one-shot process; it will not run on a schedule."
            : "Waiting for the recurring operations worker to claim this request."}
        </p>
      )}
    </div>
  );
}
