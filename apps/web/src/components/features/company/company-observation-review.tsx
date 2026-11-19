"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResearch } from "@/hooks/use-research";
import {
  isObservationProposalDecisionRead,
  isObservationProposalList,
  isObservationProposalPreviewRead,
  type ObservationProposalRead,
  type ObservationProposalPreviewRead,
} from "@/lib/domain-contracts";

type Action = "accept" | "reject";
type Item = ObservationProposalRead["proposal"]["items"][number];

function itemSummary(item: Item): string {
  if ("display_name" in item)
    return `Define ${item.display_name} · ${item.canonical_unit} × ${item.canonical_scale}`;
  if ("value" in item)
    return `${item.period_type} ${item.period_end} · ${item.value} × ${item.scale} ${item.currency ?? item.unit} (${item.value_qualifier})`;
  return `${item.period_type} ${item.period_end} · guidance ${item.lower_value ?? "?"}–${item.upper_value ?? "?"} × ${item.scale} ${item.currency ?? item.unit}`;
}

function safeSource(url: string) {
  return /^https:\/\//i.test(url) ? url : null;
}

export function ObservationProposalReview({
  companyId,
}: {
  companyId: string;
}) {
  const state = useResearch(
    `company-observation-proposals?company_id=${encodeURIComponent(companyId)}&limit=100`,
    isObservationProposalList,
  );
  const [selectedId, setSelectedId] = useState("");
  const [previews, setPreviews] = useState<
    Record<string, ObservationProposalPreviewRead>
  >({});
  const [decisions, setDecisions] = useState<
    Record<string, ObservationProposalRead>
  >({});
  const [decisionNote, setDecisionNote] = useState("");
  const [confirm, setConfirm] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const proposals = useMemo(
    () =>
      (state.data ?? [])
        .filter((row) => row.proposal.company_id === companyId)
        .map((row) => decisions[row.id] ?? row)
        .sort((a, b) => {
          const activeA =
            a.status === "ACCEPTED" || a.status === "REJECTED" ? 1 : 0;
          const activeB =
            b.status === "ACCEPTED" || b.status === "REJECTED" ? 1 : 0;
          return (
            activeA - activeB || b.submitted_at.localeCompare(a.submitted_at)
          );
        }),
    [companyId, decisions, state.data],
  );
  const selected =
    proposals.find((row) => row.id === selectedId) ?? proposals[0] ?? null;
  const preview = selected ? (previews[selected.id] ?? null) : null;
  const terminal =
    selected?.status === "ACCEPTED" || selected?.status === "REJECTED";
  const canAccept =
    Boolean(preview?.preview_fingerprint) &&
    preview?.status === "READY" &&
    !terminal &&
    decisionNote.trim().length > 0;

  function choose(id: string) {
    setSelectedId(id);
    setDecisionNote("");
    setConfirm(null);
    setMessage("");
  }

  async function review(action: "preview" | Action) {
    if (!selected || busy) return;
    if (action === "accept" && !canAccept) return;
    if (action === "reject" && (terminal || !decisionNote.trim())) return;
    if (action !== "preview" && confirm !== action) {
      setConfirm(action);
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(
        `/api/research/company-observation-proposals/${encodeURIComponent(selected.id)}/${action}`,
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
      if (!response.ok) throw new Error("Review rejected. Reload and retry.");
      if (action === "preview") {
        if (!isObservationProposalPreviewRead(data))
          throw new Error("Preview failed contract validation.");
        setPreviews((previous) => ({ ...previous, [selected.id]: data }));
        setMessage(
          data.status === "READY"
            ? "Source and canonical identities are ready for human review."
            : "Resolve the displayed issues before accepting.",
        );
      } else {
        if (!isObservationProposalDecisionRead(data))
          throw new Error("Decision failed contract validation.");
        setDecisions((previous) => ({
          ...previous,
          [selected.id]: data.proposal,
        }));
        if (data.preview)
          setPreviews((previous) => ({
            ...previous,
            [selected.id]: data.preview!,
          }));
        setMessage(
          data.status === "ACCEPTED"
            ? "Accepted as immutable canonical observation data."
            : data.status === "REJECTED"
              ? "Proposal rejected and retained for audit."
              : "Accepted state changed. Refresh the preview.",
        );
        if (data.status === "ACCEPTED")
          window.dispatchEvent(new Event("portfolio:data-refreshed"));
        setDecisionNote("");
        state.retry();
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Review failed.");
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  }

  return (
    <section aria-labelledby="observation-review-heading" className="space-y-3">
      <div>
        <h2 id="observation-review-heading" className="text-lg font-semibold">
          Operating data proposals
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Source-backed agent and Sheets submissions share one reviewer
          workflow. Preview before acceptance; no proposal changes accepted
          values automatically.
        </p>
      </div>
      {!state.data ? (
        <Card>
          <CardContent className="space-y-3 py-5 text-sm text-muted-foreground">
            <p>
              {state.error
                ? "Proposal review is unavailable. Configure the separate reviewer role on the API and web server."
                : "Loading the review queue…"}
            </p>
            <Button variant="outline" type="button" onClick={state.retry}>
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : proposals.length === 0 ? (
        <Card>
          <CardContent className="py-5 text-sm text-muted-foreground">
            No operating metric, KPI or management-guidance proposals currently
            require review.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {proposals.length} reviewable or historical proposals
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-5 lg:grid-cols-[minmax(12rem,0.4fr)_minmax(0,1fr)]">
            <div className="space-y-1">
              {proposals.map((row) => (
                <button
                  type="button"
                  key={row.id}
                  aria-pressed={selected?.id === row.id}
                  onClick={() => choose(row.id)}
                  className={`w-full rounded-md border p-3 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    selected?.id === row.id
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/40"
                  }`}
                >
                  <span className="block font-medium">
                    {row.proposal.contract_type.replace("BatchV1", "")}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {row.status} · {row.proposal.items.length} rows
                  </span>
                </button>
              ))}
            </div>
            {selected && (
              <div className="min-w-0 space-y-4 text-sm">
                <div>
                  <h3 className="font-semibold">
                    {selected.proposal.contract_type}
                  </h3>
                  <p className="text-muted-foreground">
                    {selected.proposal.rationale}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Source: {selected.producer_id} · submitted{" "}
                    {selected.submitted_at}
                  </p>
                </div>
                <ul className="divide-y rounded-md border">
                  {selected.proposal.items.map((item, index) => (
                    <li
                      key={`${index}:${item.metric_key}`}
                      className="space-y-1 px-3 py-2"
                    >
                      <div className="font-medium">{item.metric_key}</div>
                      <div>{itemSummary(item)}</div>
                      {safeSource(item.source_reference) ? (
                        <a
                          href={item.source_reference}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline-offset-2 hover:underline"
                        >
                          View primary source
                        </a>
                      ) : (
                        <span className="text-muted-foreground">
                          No verified source URL
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
                {preview && (
                  <div className="space-y-1 rounded-md border p-3">
                    <p className="font-medium">
                      Reviewer preview: {preview.status}
                    </p>
                    {preview.changes.map((change) => (
                      <p key={change.row_index} className="text-xs">
                        {change.metric_key}: {change.operation.toLowerCase()}
                        {change.previous_id ? " (explicit supersession)" : ""}
                      </p>
                    ))}
                    {preview.issues.map((issue) => (
                      <p
                        key={`${issue.row_index}:${issue.code}`}
                        className="text-xs"
                      >
                        {issue.code}: {issue.detail}
                      </p>
                    ))}
                  </div>
                )}
                {selected.issue && (
                  <p className="text-sm text-muted-foreground">
                    {selected.issue}
                  </p>
                )}
                {selected.decision_note && (
                  <p className="text-sm text-muted-foreground">
                    Recorded reviewer note: {selected.decision_note}
                  </p>
                )}
                {!terminal && (
                  <div className="space-y-3">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={busy}
                      onClick={() => void review("preview")}
                    >
                      {preview
                        ? "Refresh reviewer preview"
                        : "Preview source & conflicts"}
                    </Button>
                    <label className="block space-y-1">
                      <span className="text-xs text-muted-foreground">
                        Reviewer decision note
                      </span>
                      <textarea
                        className="w-full rounded-md border bg-background p-2"
                        rows={3}
                        maxLength={2000}
                        value={decisionNote}
                        onChange={(event) => {
                          setDecisionNote(event.target.value);
                          setConfirm(null);
                        }}
                      />
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        disabled={busy || !canAccept}
                        onClick={() => void review("accept")}
                      >
                        {confirm === "accept"
                          ? "Confirm acceptance"
                          : "Accept reviewed facts"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        disabled={busy || !decisionNote.trim()}
                        onClick={() => void review("reject")}
                      >
                        {confirm === "reject"
                          ? "Confirm rejection"
                          : "Reject proposal"}
                      </Button>
                    </div>
                    {confirm && (
                      <p
                        role="status"
                        className="text-xs text-muted-foreground"
                      >
                        Confirm this {confirm} decision by pressing the same
                        button again.
                      </p>
                    )}
                  </div>
                )}
                {message && (
                  <p role="status" className="text-sm">
                    {message}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </section>
  );
}
