"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, PendingOrError } from "@/components/app/empty-state";
import { SourceReference } from "@/components/app/source-reference";
import { StatusIndicator } from "@/components/app/status-indicator";
import { useResearch } from "@/hooks/use-research";
import {
  isModelRevisionProposalDecisionRead,
  isModelRevisionProposalList,
  isModelRevisionProposalPreviewRead,
  type ModelRevisionProposalPreviewRead,
  type ModelRevisionProposalRead,
} from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";

type Decision = "ACCEPT" | "REJECT";

function proposalStatus(
  proposal: ModelRevisionProposalRead,
  preview: ModelRevisionProposalPreviewRead | null,
) {
  if (proposal.status === "ACCEPTED" || proposal.status === "REJECTED")
    return proposal.status;
  return preview?.status ?? proposal.status;
}

function ModelProposalDiffs({
  title,
  changes,
}: {
  title: string;
  changes: NonNullable<ModelRevisionProposalPreviewRead["input_changes"]>;
}) {
  return (
    <section aria-label={title} className="space-y-2">
      <h4 className="text-sm font-semibold">{title}</h4>
      {changes.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No differences returned.
        </p>
      ) : (
        <div className="overflow-hidden rounded-md border">
          <div className="hidden grid-cols-[minmax(10rem,1fr)_minmax(5rem,0.8fr)_minmax(5rem,0.8fr)] gap-3 bg-muted/50 px-3 py-2 text-xs font-medium sm:grid">
            <span>Field</span>
            <span>Accepted</span>
            <span>Proposed</span>
          </div>
          <ul className="divide-y">
            {changes.map((change) => (
              <li
                key={`${change.field}:${change.before}:${change.after}`}
                className="grid gap-1 px-3 py-2 text-xs sm:grid-cols-[minmax(10rem,1fr)_minmax(5rem,0.8fr)_minmax(5rem,0.8fr)] sm:gap-3"
              >
                <span className="break-words font-medium">{change.field}</span>
                <span className="break-all text-muted-foreground sm:break-words">
                  {change.before ?? "Unavailable"}
                </span>
                <span className="break-all sm:break-words">
                  {change.after ?? "Unavailable"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export function ModelRevisionProposalReview({
  companyId,
}: {
  companyId: string;
}) {
  const state = useResearch(
    `model-revision-proposals?company_id=${encodeURIComponent(companyId)}&limit=100`,
    isModelRevisionProposalList,
  );
  const [selectedId, setSelectedId] = useState("");
  const [previewById, setPreviewById] = useState<
    Record<string, ModelRevisionProposalPreviewRead>
  >({});
  const [proposalOverrides, setProposalOverrides] = useState<
    Record<string, ModelRevisionProposalRead>
  >({});
  const [decisionNote, setDecisionNote] = useState("");
  const [confirmDecision, setConfirmDecision] = useState<Decision | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const proposals = useMemo(
    () =>
      (state.data ?? [])
        .filter((item) => item.proposal.company_id === companyId)
        .map((item) => proposalOverrides[item.id] ?? item),
    [companyId, proposalOverrides, state.data],
  );
  const selected =
    proposals.find((item) => item.id === selectedId) ?? proposals[0] ?? null;
  const preview = selected ? (previewById[selected.id] ?? null) : null;
  const status = selected ? proposalStatus(selected, preview) : null;
  const terminal = status === "ACCEPTED" || status === "REJECTED";
  const canAccept =
    status === "READY" && Boolean(preview?.preview_fingerprint) && !terminal;

  function selectProposal(id: string) {
    setSelectedId(id);
    setDecisionNote("");
    setConfirmDecision(null);
    setError("");
    setMessage("");
  }

  async function review(action: "preview" | "accept" | "reject") {
    if (!selected) return;
    if (action === "accept" && (!canAccept || !decisionNote.trim())) return;
    if (action === "reject" && !decisionNote.trim()) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch(
        `/api/research/model-revision-proposals/${encodeURIComponent(selected.id)}/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          ...(action === "accept"
            ? {
                body: JSON.stringify({
                  preview_fingerprint: preview?.preview_fingerprint,
                  decision_note: decisionNote.trim(),
                }),
              }
            : action === "reject"
              ? { body: JSON.stringify({ decision_note: decisionNote.trim() }) }
              : {}),
        },
      );
      const data: unknown = await response.json();
      if (!response.ok) {
        const detail =
          typeof data === "object" && data !== null && "detail" in data
            ? String(data.detail)
            : "The model proposal review could not be completed.";
        throw new Error(detail);
      }
      if (action === "preview") {
        if (!isModelRevisionProposalPreviewRead(data))
          throw new Error("The preview did not match the model contract.");
        setPreviewById((current) => ({ ...current, [selected.id]: data }));
        setMessage(
          data.status === "READY"
            ? "Native calculation preview is ready. No accepted model was changed."
            : (data.reason ??
                "The proposal requires review before acceptance."),
        );
      } else {
        if (!isModelRevisionProposalDecisionRead(data))
          throw new Error(
            "The review response did not match the model contract.",
          );
        setProposalOverrides((current) => ({
          ...current,
          [selected.id]: data.proposal,
        }));
        if (data.preview) {
          setPreviewById((current) => ({
            ...current,
            [selected.id]: data.preview!,
          }));
        }
        setConfirmDecision(null);
        setDecisionNote("");
        setMessage(
          action === "accept"
            ? data.status === "ACCEPTED"
              ? "Accepted as a new immutable canonical model revision."
              : (data.preview?.reason ??
                "The proposal needs a refreshed preview.")
            : "Proposal rejected; the review decision is retained.",
        );
        if (action === "accept" && data.status === "ACCEPTED")
          window.dispatchEvent(new Event("portfolio:data-refreshed"));
        state.retry();
      }
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The model proposal review could not be completed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="model-proposals-title" className="space-y-3">
      <div>
        <h2 id="model-proposals-title" className="text-lg font-semibold">
          Agent model proposals
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Proposals remain separate from accepted assumptions until an
          authenticated reviewer previews and confirms a decision.
        </p>
      </div>

      {!state.data ? (
        state.error ? (
          <EmptyState
            title="Model proposal review is unavailable"
            description="Confirm the proposal-review API migration, MODEL_PROPOSAL_REVIEWER_TOKEN and MODEL_PROPOSAL_REVIEWER_ID on the API, and the matching MODEL_PROPOSAL_REVIEWER_TOKEN on the web server. No proposal decision has been submitted."
            actions={
              <Button type="button" variant="outline" onClick={state.retry}>
                Retry proposal review
              </Button>
            }
          />
        ) : (
          <PendingOrError error={undefined} retry={state.retry} />
        )
      ) : proposals.length === 0 ? (
        <EmptyState
          title="No model proposals for this company"
          description="Agent-authored changes appear here after submission. Imported Sheets packages and accepted revisions remain in their existing model history."
        />
      ) : (
        <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(14rem,0.7fr)_minmax(0,1.7fr)]">
          <Card className="min-w-0 shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">
                Review queue · {proposals.length}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {proposals.map((item) => {
                const itemStatus = proposalStatus(
                  item,
                  previewById[item.id] ?? null,
                );
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={selected?.id === item.id}
                    onClick={() => selectProposal(item.id)}
                    className={`w-full rounded-md border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selected?.id === item.id ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}
                  >
                    <span className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium">
                        {item.proposal.external_revision_id}
                      </span>
                      <StatusIndicator status={itemStatus} />
                    </span>
                    <span className="mt-2 block text-xs text-muted-foreground">
                      {item.proposal.method.methodology.replaceAll("_", " ")} ·{" "}
                      {dateTime(item.submitted_at)}
                    </span>
                  </button>
                );
              })}
            </CardContent>
          </Card>

          {selected && (
            <Card className="min-w-0 shadow-none">
              <CardHeader className="gap-3 pb-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusIndicator status={status ?? selected.status} />
                    <Badge variant="outline">
                      {selected.proposal.methodology_version}
                    </Badge>
                    <Badge variant="secondary">
                      {selected.proposal.model_currency}
                    </Badge>
                  </div>
                  <CardTitle className="mt-2 break-words text-base">
                    {selected.proposal.external_revision_id}
                  </CardTitle>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy || terminal}
                  onClick={() => void review("preview")}
                >
                  {busy
                    ? "Working…"
                    : preview
                      ? "Refresh preview"
                      : "Preview changes"}
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                <dl className="grid gap-3 rounded-md border bg-muted/20 p-3 text-xs sm:grid-cols-2 xl:grid-cols-3">
                  <Meta
                    label="Canonical base revision"
                    value={`${selected.proposal.base_revision_number} · ${selected.proposal.base_revision_id}`}
                  />
                  <Meta
                    label="Model identity"
                    value={selected.proposal.model_id}
                  />
                  <Meta
                    label="Exact listing"
                    value={selected.proposal.valuation_listing_id}
                  />
                  <Meta
                    label="Producer / author"
                    value={selected.producer_id}
                  />
                  <Meta
                    label="Authored"
                    value={dateTime(selected.proposal.authored_at)}
                  />
                  <Meta
                    label="Received by app"
                    value={dateTime(selected.submitted_at)}
                  />
                  {selected.reviewer_id && (
                    <Meta label="Reviewed by" value={selected.reviewer_id} />
                  )}
                  {selected.accepted_revision_id && (
                    <Meta
                      label="Accepted revision"
                      value={selected.accepted_revision_id}
                    />
                  )}
                </dl>

                <div className="space-y-1">
                  <h3 className="text-sm font-semibold">Rationale</h3>
                  <p className="whitespace-pre-wrap text-sm leading-6">
                    {selected.proposal.rationale}
                  </p>
                </div>
                <SourceReference
                  href={selected.proposal.source_reference}
                  label="Open source evidence"
                />
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">
                    Canonical evidence links
                  </h3>
                  <ul className="space-y-2">
                    {selected.proposal.supporting_evidence.map((evidence) => (
                      <li
                        key={`${evidence.evidence_type}:${evidence.reference_id}`}
                        className="rounded-md border p-3 text-xs"
                      >
                        <p className="font-medium">
                          {evidence.evidence_type.replaceAll("_", " ")} ·{" "}
                          {evidence.relationship}
                        </p>
                        <p className="mt-1 break-all text-muted-foreground">
                          {evidence.reference_id}
                        </p>
                        {evidence.note && (
                          <p className="mt-1 text-foreground">
                            {evidence.note}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>

                {(selected.issue || preview?.reason) && (
                  <p
                    role="alert"
                    className="rounded-md border border-warning/40 bg-warning/5 p-3 text-sm"
                  >
                    {preview?.reason ?? selected.issue}
                  </p>
                )}
                {preview && (
                  <div className="space-y-4 border-t pt-4">
                    <p className="text-xs text-muted-foreground">
                      Deterministic native-engine preview ·{" "}
                      {dateTime(preview.previewed_at)}
                      {preview.current_revision_number
                        ? ` · based on revision ${preview.current_revision_number}`
                        : ""}
                    </p>
                    <ModelProposalDiffs
                      title="Assumption changes"
                      changes={preview.input_changes ?? []}
                    />
                    <ModelProposalDiffs
                      title="Recalculated output changes"
                      changes={preview.output_changes ?? []}
                    />
                    <p className="text-xs text-muted-foreground">
                      Full method-specific assumptions and projections remain
                      available in the accepted model editor. Imported output
                      snapshots are not accepted model inputs.
                    </p>
                  </div>
                )}
                {!preview && !terminal && (
                  <p className="rounded-md border bg-muted/30 p-3 text-xs leading-5 text-muted-foreground">
                    Run a deterministic preview first. Acceptance remains
                    disabled until the server confirms the proposal is based on
                    the current canonical revision.
                  </p>
                )}
                {selected.decision_note && (
                  <p className="rounded-md border p-3 text-sm">
                    Reviewer note: {selected.decision_note}
                  </p>
                )}

                {!terminal && (
                  <div className="space-y-3 border-t pt-4">
                    <label className="block space-y-1.5 text-xs font-medium">
                      Review decision note
                      <textarea
                        value={decisionNote}
                        onChange={(event) =>
                          setDecisionNote(event.target.value)
                        }
                        rows={3}
                        maxLength={2000}
                        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                        placeholder="Record why you accept or reject this change."
                      />
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {confirmDecision === "ACCEPT" ? (
                        <>
                          <Button
                            type="button"
                            disabled={
                              busy || !canAccept || !decisionNote.trim()
                            }
                            onClick={() => void review("accept")}
                          >
                            {busy ? "Accepting…" : "Confirm acceptance"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busy}
                            onClick={() => setConfirmDecision(null)}
                          >
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <Button
                          type="button"
                          disabled={!canAccept || !decisionNote.trim() || busy}
                          onClick={() => setConfirmDecision("ACCEPT")}
                        >
                          Accept revision
                        </Button>
                      )}
                      {confirmDecision === "REJECT" ? (
                        <>
                          <Button
                            type="button"
                            variant="destructive"
                            disabled={busy || !decisionNote.trim()}
                            onClick={() => void review("reject")}
                          >
                            {busy ? "Rejecting…" : "Confirm rejection"}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            disabled={busy}
                            onClick={() => setConfirmDecision(null)}
                          >
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <Button
                          type="button"
                          variant="outline"
                          disabled={busy || !decisionNote.trim()}
                          onClick={() => setConfirmDecision("REJECT")}
                        >
                          Reject proposal
                        </Button>
                      )}
                    </div>
                    {confirmDecision && (
                      <p
                        role="status"
                        className="text-xs text-muted-foreground"
                      >
                        Confirm {confirmDecision.toLowerCase()} for external
                        revision {selected.proposal.external_revision_id}. This
                        decision is recorded in canonical review history.
                      </p>
                    )}
                  </div>
                )}
                {error && (
                  <p
                    role="alert"
                    className="rounded-md border border-destructive/40 p-3 text-sm"
                  >
                    {error}
                  </p>
                )}
                {message && (
                  <p role="status" className="rounded-md border p-3 text-sm">
                    {message}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </section>
  );
}

function Meta({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-all font-medium">{value ?? "Unavailable"}</dd>
    </div>
  );
}
