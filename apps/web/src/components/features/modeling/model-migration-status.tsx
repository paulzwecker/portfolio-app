import type { FinancialModelEvidenceRead } from "@/lib/domain-contracts";
import { date } from "@/lib/display";

type Props = {
  authorId?: string | null;
  authoredAt?: string | null;
  sourceReference?: string | null;
  evidence?: FinancialModelEvidenceRead[];
  compact?: boolean;
};

export function FinancialModelProposalEvidence({
  authorId,
  authoredAt,
  sourceReference,
  evidence = [],
  compact = false,
}: Props) {
  if (!authorId && !authoredAt && !sourceReference && evidence.length === 0)
    return null;

  return (
    <section
      aria-label="Research evidence for model proposal"
      className={`rounded-md border bg-muted/20 ${compact ? "p-3" : "p-4"}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold">
          Research basis for the proposal
        </h4>
        <p className="text-xs text-muted-foreground">
          Agent interpretation and proposed assumptions remain distinct from
          these published records.
        </p>
      </div>
      {(authorId || authoredAt || sourceReference) && (
        <dl className="mt-3 grid gap-x-4 gap-y-2 text-xs sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Proposed by</dt>
            <dd className="mt-0.5 break-words">
              {authorId ?? "Unknown author"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Authored</dt>
            <dd className="mt-0.5">
              {authoredAt ? date(authoredAt) : "Not recorded"}
            </dd>
          </div>
          {sourceReference && (
            <div>
              <dt className="text-muted-foreground">Proposal source</dt>
              <dd className="mt-0.5">
                <a
                  href={sourceReference}
                  target="_blank"
                  rel="noreferrer"
                  className="break-all text-primary hover:underline"
                >
                  Open source
                </a>
              </dd>
            </div>
          )}
        </dl>
      )}
      {evidence.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {evidence.map((item) => (
            <li
              key={`${item.evidence_type}-${item.reference_id}`}
              className="grid gap-2 rounded-md border bg-background p-3 sm:grid-cols-[minmax(0,1fr)_auto]"
            >
              <div className="min-w-0">
                <p className="text-xs font-medium">
                  {item.evidence_type.replaceAll("_", " ")} ·{" "}
                  {item.relationship}
                  {" · "}
                  {item.evidence_status.replaceAll("_", " ")}
                </p>
                {item.summary && (
                  <p className="mt-1 break-words text-sm leading-5">
                    {item.summary}
                  </p>
                )}
                {item.note && (
                  <p className="mt-1 break-words text-xs text-muted-foreground">
                    {item.note}
                  </p>
                )}
                {item.trigger_references?.length ? (
                  <div className="mt-2 border-t pt-2">
                    <p className="text-[11px] font-medium">Trigger lineage</p>
                    <ul className="mt-1 space-y-1">
                      {item.trigger_references.map((trigger) => (
                        <li key={trigger.trigger_id} className="text-xs">
                          <span className="font-medium">
                            {trigger.classification.replaceAll("-", " ")} ·{" "}
                            {trigger.title}
                          </span>
                          <span className="block text-muted-foreground">
                            {trigger.classification_rationale}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {item.resolution_issue && (
                  <p className="mt-1 text-xs text-destructive">
                    {item.resolution_issue}
                  </p>
                )}
                <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                  {item.reference_id}
                  {item.author_id ? ` · ${item.author_id}` : ""}
                  {item.recorded_at
                    ? ` · recorded ${date(item.recorded_at)}`
                    : ""}
                </p>
              </div>
              {item.source_reference && (
                <a
                  href={item.source_reference}
                  target="_blank"
                  rel="noreferrer"
                  className="self-start text-xs text-primary hover:underline"
                >
                  View published record
                </a>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-amber-800">
          No canonical research or thesis evidence was attached.
        </p>
      )}
    </section>
  );
}
