"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusIndicator } from "@/components/app/status-indicator";
import { SourceReference } from "@/components/app/source-reference";
import {
  isGoogleSheetsResearchCandidate,
  isGoogleSheetsResearchSyncCheck,
  isGoogleSheetsRiskCandidate,
  isGoogleSheetsRiskSyncCheck,
  isGoogleSheetsSyncCandidate,
  isGoogleSheetsSyncCheck,
  isUniverse,
  type Company,
  type GoogleSheetsResearchCandidate,
  type GoogleSheetsRiskCandidate,
  type GoogleSheetsSyncCandidate,
} from "@/lib/domain-contracts";
import { useResearch } from "@/hooks/use-research";
import { date } from "@/lib/display";

type ProposalKind = "MODEL" | "RESEARCH" | "RISK";
type Candidate =
  | GoogleSheetsSyncCandidate
  | GoogleSheetsResearchCandidate
  | GoogleSheetsRiskCandidate;
type Proposal = {
  key: string;
  kind: ProposalKind;
  id: string;
  title: string;
  companyId: string | null;
  companyName: string;
  lifecycle: Company["lifecycle"] | null;
  status: string;
  contractVersion: string | null;
  externalRevision: string | null;
  baseRevision: string | null;
  author: string | null;
  sourceId: string | null;
  sourceUrl: string;
  rationale: string | null;
  issue: string | null;
  observedAt: string | null;
  recordedAt: string;
  reviewer: string | null;
  reviewNote: string | null;
  decisionAt: string | null;
  acceptedRevisionIds: string[];
  preview: Record<string, unknown> | null;
  candidate: Candidate;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function displayValue(value: unknown) {
  if (value === null || value === undefined) return "Unavailable";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return JSON.stringify(value);
}

function toProposal(
  kind: ProposalKind,
  candidate: Candidate,
  companyById: Map<string, Company>,
  prior?: Proposal,
): Proposal {
  const key = kind + ":" + candidate.id;
  if (kind === "MODEL") {
    const value = candidate as GoogleSheetsSyncCandidate;
    return {
      key,
      kind,
      id: value.id,
      title:
        (value.company_name ?? "Company not mapped") +
        " · " +
        (value.model_name ?? "Model"),
      companyId: value.company_id,
      companyName:
        value.company_name ??
        (value.company_id ? companyById.get(value.company_id)?.name : null) ??
        prior?.companyName ??
        "Company identity unavailable",
      lifecycle: value.company_id
        ? (companyById.get(value.company_id)?.lifecycle ??
          prior?.lifecycle ??
          null)
        : (prior?.lifecycle ?? null),
      status: value.status,
      contractVersion: value.contract_version,
      externalRevision: value.external_revision_id,
      baseRevision: value.base_revision_id,
      author: value.proposal?.author_id ?? null,
      sourceId: value.proposal?.source_reference ?? prior?.sourceId ?? null,
      sourceUrl: value.source_url,
      rationale: value.rationale,
      issue: value.issue,
      observedAt: value.proposal?.authored_at ?? null,
      recordedAt: value.last_observed_at,
      reviewer: value.reviewer,
      reviewNote: value.decision_note,
      decisionAt: value.accepted_at ?? value.rejected_at,
      acceptedRevisionIds: value.accepted_revision_id
        ? [value.accepted_revision_id]
        : [],
      preview: value.preview_data,
      candidate,
    };
  }
  if (kind === "RESEARCH") {
    const value = candidate as GoogleSheetsResearchCandidate;
    const company = value.company_id ? companyById.get(value.company_id) : null;
    return {
      key,
      kind,
      id: value.id,
      title:
        (value.domain === "THESIS" ? "Thesis revision" : "Research forecast") +
        (value.stream_key ? " · " + value.stream_key : ""),
      companyId: value.company_id,
      companyName:
        company?.name ?? prior?.companyName ?? "Company identity unavailable",
      lifecycle: company?.lifecycle ?? prior?.lifecycle ?? null,
      status: value.status,
      contractVersion: value.contract_version,
      externalRevision: value.external_revision_id,
      baseRevision: value.base_revision_id,
      author: value.author_id,
      sourceId: value.source_id ?? prior?.sourceId ?? null,
      sourceUrl: value.source_url,
      rationale: value.rationale,
      issue: value.issue,
      observedAt: value.observed_at,
      recordedAt: value.last_observed_at,
      reviewer: value.reviewer,
      reviewNote: value.reviewer_note,
      decisionAt: value.accepted_at ?? value.rejected_at,
      acceptedRevisionIds: [
        value.accepted_research_revision_id,
        value.accepted_thesis_revision_id,
      ].filter((id): id is string => Boolean(id)),
      preview: value.preview_data,
      candidate,
    };
  }
  const value = candidate as GoogleSheetsRiskCandidate;
  return {
    key,
    kind,
    id: value.id,
    title: value.summary ?? "Portfolio risk assessment",
    companyId: null,
    companyName: "Portfolio assessment",
    lifecycle: "PORTFOLIO",
    status: value.status,
    contractVersion: value.contract_version,
    externalRevision: value.external_revision_id,
    baseRevision: null,
    author: value.author_id,
    sourceId: value.source_id ?? prior?.sourceId ?? null,
    sourceUrl: value.source_url,
    rationale: value.summary,
    issue: value.issue,
    observedAt: value.authored_at,
    recordedAt: value.last_observed_at,
    reviewer: value.reviewer,
    reviewNote: value.reviewer_note,
    decisionAt: value.accepted_at ?? value.rejected_at,
    acceptedRevisionIds: value.accepted_revision_id
      ? [value.accepted_revision_id]
      : [],
    preview: value.preview_data,
    candidate,
  };
}

export function ProposalReviewPanel({
  modelCandidates,
  researchCandidates,
  riskCandidates,
  retry,
}: {
  modelCandidates?: GoogleSheetsSyncCandidate[];
  researchCandidates?: GoogleSheetsResearchCandidate[];
  riskCandidates?: GoogleSheetsRiskCandidate[];
  retry: () => void;
}) {
  const [view, setView] = useState<"OPEN" | "HISTORY">("OPEN");
  const [lifecycle, setLifecycle] = useState("");
  const [search, setSearch] = useState("");
  const [selectedKey, setSelectedKey] = useState("");
  const [overrides, setOverrides] = useState<Record<string, Proposal>>({});
  const [reviewMessage, setReviewMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState("");
  const [checkError, setCheckError] = useState("");
  const universe = useResearch("universe", isUniverse);
  const companyById = useMemo(
    () =>
      new Map((universe.data ?? []).map((company) => [company.id, company])),
    [universe.data],
  );
  const proposals = useMemo(() => {
    const fresh = [
      ...(modelCandidates ?? []).map((item) =>
        toProposal("MODEL", item, companyById),
      ),
      ...(researchCandidates ?? []).map((item) =>
        toProposal("RESEARCH", item, companyById),
      ),
      ...(riskCandidates ?? []).map((item) =>
        toProposal("RISK", item, companyById),
      ),
    ].map((item) => overrides[item.key] ?? item);
    return fresh
      .filter((item) => {
        const historical = ["ACCEPTED", "REJECTED"].includes(item.status);
        if (view === "OPEN" && historical) return false;
        if (view === "HISTORY" && !historical) return false;
        if (lifecycle && item.lifecycle !== lifecycle) return false;
        return (
          !search.trim() ||
          (item.title + " " + item.companyName + " " + (item.author ?? ""))
            .toLowerCase()
            .includes(search.trim().toLowerCase())
        );
      })
      .sort((left, right) => right.recordedAt.localeCompare(left.recordedAt));
  }, [
    modelCandidates,
    researchCandidates,
    riskCandidates,
    companyById,
    view,
    lifecycle,
    search,
    overrides,
  ]);

  const pendingCount = proposals.filter((item) =>
    ["PENDING", "READY", "STALE_BASELINE", "CONFLICT", "INVALID"].includes(
      item.status,
    ),
  ).length;

  async function checkInboxes() {
    setChecking(true);
    setCheckError("");
    setCheckResult("");
    const endpoints = [
      "google-sheets-sync/check",
      "google-sheets-research-sync/check",
      "google-sheets-risk-sync/check",
    ];
    try {
      const results = await Promise.all(
        endpoints.map(async (endpoint) => {
          const response = await fetch("/api/research/" + endpoint, {
            method: "POST",
            cache: "no-store",
          });
          const value: unknown = await response.json();
          if (!response.ok)
            throw new Error(
              typeof value === "object" && value !== null && "detail" in value
                ? String(value.detail)
                : "An inbox check failed.",
            );
          return value;
        }),
      );
      const [modelCheck, researchCheck, riskCheck] = results;
      if (
        !isGoogleSheetsSyncCheck(modelCheck) ||
        !isGoogleSheetsResearchSyncCheck(researchCheck) ||
        !isGoogleSheetsRiskSyncCheck(riskCheck)
      ) {
        throw new Error(
          "At least one inbox returned a response outside its contract.",
        );
      }
      const discovered =
        modelCheck.new_candidates.length +
        researchCheck.new_candidates.length +
        riskCheck.new_candidates.length;
      setCheckResult(
        "All three inboxes checked; " +
          discovered +
          " new candidate(s) detected. Nothing was accepted.",
      );
      retry();
    } catch (failure) {
      setCheckError(
        failure instanceof Error ? failure.message : "Inbox checks failed.",
      );
      retry();
    } finally {
      setChecking(false);
    }
  }

  function updateProposal(next: Proposal, message: string) {
    setOverrides((current) => ({ ...current, [next.key]: next }));
    setReviewMessage(message);
  }

  const selected =
    proposals.find((item) => item.key === selectedKey) ?? proposals[0];
  return (
    <section aria-labelledby="proposal-review-heading" className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="proposal-review-heading" className="text-lg font-semibold">
            Agent proposal review
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Model, research, thesis, and portfolio-risk submissions share one
            review queue. Delivery and agent acknowledgment are not approval.
          </p>
        </div>
        <Button
          variant="outline"
          disabled={checking}
          onClick={() => void checkInboxes()}
        >
          {checking ? "Checking inboxes…" : "Check all inboxes"}
        </Button>
      </div>
      {checkResult && (
        <p role="status" className="rounded-md border p-3 text-sm">
          {checkResult}
        </p>
      )}
      {checkError && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 p-3 text-sm"
        >
          {checkError}
        </p>
      )}
      {reviewMessage && (
        <p
          role="status"
          className="rounded-md border border-positive/30 bg-positive/5 p-3 text-sm"
        >
          {reviewMessage}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">
          {pendingCount} proposals awaiting a decision
        </Badge>
        <button
          type="button"
          aria-pressed={view === "OPEN"}
          onClick={() => setView("OPEN")}
          className={
            view === "OPEN"
              ? "rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground"
              : "rounded-md border px-3 py-2 text-sm"
          }
        >
          Needs review
        </button>
        <button
          type="button"
          aria-pressed={view === "HISTORY"}
          onClick={() => setView("HISTORY")}
          className={
            view === "HISTORY"
              ? "rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground"
              : "rounded-md border px-3 py-2 text-sm"
          }
        >
          Review history
        </button>
        <label className="grid gap-1 text-xs font-medium sm:ml-auto">
          Lifecycle context
          <select
            value={lifecycle}
            onChange={(event) => setLifecycle(event.target.value)}
            className="h-9 rounded-md border bg-background px-3 text-sm"
          >
            <option value="">All contexts</option>
            <option value="PORTFOLIO">Portfolio</option>
            <option value="WATCHLIST">Watchlist</option>
            <option value="CANDIDATE">Candidate</option>
          </select>
        </label>
        <label className="grid min-w-48 flex-1 gap-1 text-xs font-medium">
          Search proposals
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="h-9 rounded-md border bg-background px-3 text-sm"
            placeholder="Company, stream, author"
          />
        </label>
      </div>

      {universe.error && (
        <p className="text-xs text-muted-foreground">
          Company names are unavailable for some submissions; canonical company
          IDs and source references remain visible.
        </p>
      )}
      {proposals.length === 0 ? (
        <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          {view === "OPEN"
            ? "No pending or conflicted submissions were returned by the connected inboxes."
            : "No accepted or rejected proposal history was returned."}
        </p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(250px,0.82fr)_minmax(0,1.5fr)]">
          <div className="space-y-2" aria-label="Research proposals">
            {proposals.map((item) => (
              <button
                key={item.key}
                type="button"
                aria-pressed={item.key === (selected?.key ?? "")}
                onClick={() => setSelectedKey(item.key)}
                className={
                  "w-full rounded-md border p-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
                  (item.key === selected?.key
                    ? "border-primary bg-primary/5"
                    : "hover:bg-muted/50")
                }
              >
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{item.companyName}</span>
                  <StatusIndicator status={item.status} />
                </span>
                <span className="mt-1 block text-sm">{item.title}</span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {item.kind} ·{" "}
                  {item.externalRevision ?? "external revision unavailable"}
                </span>
              </button>
            ))}
          </div>
          {selected && (
            <ProposalDetail
              key={selected.key}
              proposal={selected}
              onUpdated={updateProposal}
            />
          )}
        </div>
      )}
    </section>
  );
}

function ProposalDetail({
  proposal,
  onUpdated,
}: {
  proposal: Proposal;
  onUpdated: (proposal: Proposal, message: string) => void;
}) {
  const [reviewer, setReviewer] = useState("Local reviewer");
  const [note, setNote] = useState("");
  const [ackStale, setAckStale] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState<"ACCEPT" | "REJECT" | null>(null);
  const canPreview = !["ACCEPTED", "REJECTED"].includes(proposal.status);
  const isStaleRisk =
    proposal.kind === "RISK" && proposal.status === "STALE_BASELINE";
  const hasPreview = proposal.preview !== null;
  const canAccept =
    hasPreview && (proposal.status === "READY" || (isStaleRisk && ackStale));
  const canReject = !["ACCEPTED", "REJECTED"].includes(proposal.status);

  async function action(actionType: "preview" | "accept" | "reject") {
    setPending(true);
    setError("");
    try {
      const domain =
        proposal.kind === "MODEL"
          ? "google-sheets-sync"
          : proposal.kind === "RISK"
            ? "google-sheets-risk-sync"
            : "google-sheets-research-sync";
      const body =
        actionType === "accept"
          ? proposal.kind === "MODEL"
            ? { reviewer: reviewer.trim(), decision_note: note.trim() }
            : proposal.kind === "RISK"
              ? {
                  reviewer: reviewer.trim(),
                  reviewer_note: note.trim(),
                  acknowledge_stale_baseline: ackStale,
                }
              : { reviewer: reviewer.trim(), reviewer_note: note.trim() }
          : actionType === "reject"
            ? proposal.kind === "MODEL"
              ? { reviewer: reviewer.trim(), decision_note: note.trim() }
              : { reviewer: reviewer.trim(), reviewer_note: note.trim() }
            : undefined;
      const response = await fetch(
        "/api/research/" +
          domain +
          "/candidates/" +
          encodeURIComponent(proposal.id) +
          "/" +
          actionType,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          ...(body ? { body: JSON.stringify(body) } : {}),
        },
      );
      const result: unknown = await response.json();
      if (!response.ok) {
        const detail =
          isRecord(result) && "detail" in result
            ? String(result.detail)
            : "The proposal review could not be completed.";
        throw new Error(detail);
      }
      let next: Proposal;
      if (proposal.kind === "MODEL" && isGoogleSheetsSyncCandidate(result)) {
        next = toProposal("MODEL", result, new Map(), proposal);
      } else if (
        proposal.kind === "RISK" &&
        isGoogleSheetsRiskCandidate(result)
      ) {
        next = toProposal("RISK", result, new Map(), proposal);
      } else if (
        proposal.kind === "RESEARCH" &&
        isGoogleSheetsResearchCandidate(result)
      ) {
        next = toProposal("RESEARCH", result, new Map(), proposal);
      } else {
        throw new Error(
          "The proposal response did not match its domain contract.",
        );
      }
      setConfirm(null);
      onUpdated(
        next,
        actionType === "preview"
          ? "Preview refreshed from the existing domain validator."
          : actionType === "accept"
            ? "Accepted into canonical history."
            : "Rejected with the reviewer decision retained.",
      );
      if (actionType !== "preview") setNote("");
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The proposal review could not be completed.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{proposal.kind}</Badge>
              <StatusIndicator status={proposal.status} />
              {proposal.contractVersion && (
                <Badge variant="outline">
                  Contract {proposal.contractVersion}
                </Badge>
              )}
            </div>
            <h3 className="mt-2 text-base font-semibold">{proposal.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {proposal.companyName}
            </p>
          </div>
          {proposal.companyId && (
            <Link
              href={"/company/" + encodeURIComponent(proposal.companyId)}
              className="text-sm text-primary underline-offset-4 hover:underline"
            >
              Open Company Explorer
            </Link>
          )}
        </div>

        <dl className="grid gap-3 rounded-md border bg-muted/20 p-3 text-xs sm:grid-cols-2 lg:grid-cols-3">
          <Meta label="External revision" value={proposal.externalRevision} />
          <Meta label="Canonical base revision" value={proposal.baseRevision} />
          <Meta label="Author" value={proposal.author} />
          <Meta
            label="Observed / authored"
            value={proposal.observedAt ? date(proposal.observedAt) : null}
          />
          <Meta
            label="Application recorded"
            value={date(proposal.recordedAt)}
          />
          <Meta label="Source identity" value={proposal.sourceId} />
          {["ACCEPTED", "REJECTED"].includes(proposal.status) && (
            <>
              <Meta label="Reviewed by" value={proposal.reviewer} />
              <Meta
                label="Decision recorded"
                value={proposal.decisionAt ? date(proposal.decisionAt) : null}
              />
              <Meta
                label="Canonical revision"
                value={proposal.acceptedRevisionIds.join(" · ") || null}
              />
            </>
          )}
        </dl>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Rationale
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm">
            {proposal.rationale ?? "No rationale supplied."}
          </p>
        </div>
        {["ACCEPTED", "REJECTED"].includes(proposal.status) &&
          proposal.reviewNote && (
            <p className="rounded-md border p-3 text-sm">
              <span className="font-medium">Reviewer rationale: </span>
              {proposal.reviewNote}
            </p>
          )}
        {proposal.sourceUrl && (
          <SourceReference
            href={proposal.sourceUrl}
            label="Open source publication"
          />
        )}
        {proposal.issue && (
          <p
            role="alert"
            className="rounded-md border border-warning/40 bg-warning/5 p-3 text-sm"
          >
            {proposal.issue}
          </p>
        )}
        {proposal.kind === "MODEL" && (
          <ModelEvidence
            candidate={proposal.candidate as GoogleSheetsSyncCandidate}
          />
        )}
        {proposal.kind === "RISK" && isStaleRisk && (
          <p className="rounded-md border border-warning/40 bg-warning/5 p-3 text-sm">
            This risk assessment uses a stale portfolio baseline. The cited
            holdings snapshot and valuation time remain historical.
          </p>
        )}
        <PreviewDetails data={proposal.preview} />

        {canPreview && (
          <Button
            type="button"
            variant="outline"
            disabled={pending}
            onClick={() => void action("preview")}
          >
            {pending
              ? "Working…"
              : hasPreview
                ? "Refresh preview"
                : "Preview changes"}
          </Button>
        )}
        {canReject && (
          <div className="grid gap-3 border-t pt-4 sm:grid-cols-2">
            <label className="grid gap-1 text-xs font-medium">
              Reviewer
              <input
                value={reviewer}
                onChange={(event) => setReviewer(event.target.value)}
                className="h-10 rounded-md border bg-background px-3 text-sm"
              />
            </label>
            <label className="grid gap-1 text-xs font-medium sm:col-span-2">
              Review rationale
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                className="min-h-16 rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="Explain the acceptance or rejection decision."
              />
            </label>
            {isStaleRisk && (
              <label className="flex items-start gap-2 text-xs sm:col-span-2">
                <input
                  type="checkbox"
                  checked={ackStale}
                  onChange={(event) => setAckStale(event.target.checked)}
                  className="mt-0.5 size-4"
                />
                I reviewed and explicitly acknowledge the stale portfolio
                baseline.
              </label>
            )}
            <div className="flex flex-wrap gap-2 sm:col-span-2">
              {confirm === "ACCEPT" ? (
                <>
                  <Button
                    type="button"
                    disabled={
                      pending || !canAccept || !reviewer.trim() || !note.trim()
                    }
                    onClick={() => void action("accept")}
                  >
                    {pending ? "Accepting…" : "Confirm acceptance"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setConfirm(null)}
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  disabled={
                    !canAccept || !reviewer.trim() || !note.trim() || pending
                  }
                  onClick={() => setConfirm("ACCEPT")}
                >
                  Accept proposal
                </Button>
              )}
              {confirm === "REJECT" ? (
                <>
                  <Button
                    type="button"
                    variant="destructive"
                    disabled={pending || !reviewer.trim() || !note.trim()}
                    onClick={() => void action("reject")}
                  >
                    {pending ? "Rejecting…" : "Confirm rejection"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setConfirm(null)}
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  variant="destructive"
                  disabled={!reviewer.trim() || !note.trim() || pending}
                  onClick={() => setConfirm("REJECT")}
                >
                  Reject proposal
                </Button>
              )}
            </div>
            {!canAccept && (
              <p className="text-xs text-muted-foreground sm:col-span-2">
                Acceptance is unavailable until the domain preview is ready.
                Conflicts, invalid contracts, and unsupported methods remain
                blocked.
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
      </CardContent>
    </Card>
  );
}

function Meta({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value ?? "Unavailable"}</dd>
    </div>
  );
}

function ModelEvidence({
  candidate,
}: {
  candidate: GoogleSheetsSyncCandidate;
}) {
  const evidence = candidate.supporting_evidence ?? [];
  return (
    <section
      aria-labelledby="model-proposal-evidence"
      className="rounded-md border p-3"
    >
      <h4 id="model-proposal-evidence" className="text-sm font-semibold">
        Research basis for the proposal
      </h4>
      <p className="mt-1 text-xs text-muted-foreground">
        {candidate.model_type ?? "Method unavailable"} ·{" "}
        {candidate.model_currency ?? "Currency unavailable"} · exact listing{" "}
        {candidate.valuation_listing_id ?? "unresolved"}
      </p>
      {evidence.length ? (
        <ul className="mt-3 space-y-2">
          {evidence.map((item, index) => (
            <li
              key={item.reference_id + ":" + index}
              className="rounded border p-2 text-xs"
            >
              <p className="font-medium">{item.summary}</p>
              {item.note && <p className="mt-1">{item.note}</p>}
              <p className="mt-1 text-muted-foreground">
                {item.evidence_type} · {item.evidence_status} · observed{" "}
                {item.observed_at ? date(item.observed_at) : "time unavailable"}
              </p>
              {item.source_reference && (
                <SourceReference
                  href={item.source_reference}
                  label="Evidence source"
                />
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">
          No supporting research evidence was linked to this model proposal.
        </p>
      )}
    </section>
  );
}

function PreviewDetails({ data }: { data: Record<string, unknown> | null }) {
  if (!data) {
    return (
      <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        No import preview has been recorded. Preview is required before
        acceptance.
      </p>
    );
  }
  const groups: [string, string][] = [
    ["changes", "Assumption changes"],
    ["projection_changes", "Projection changes"],
    ["output_changes", "Valuation and output changes"],
    ["finding_changes", "Risk finding changes"],
  ];
  const hasDiffs = groups.some(([key]) => Array.isArray(data[key]));
  const forecasts = recordRows(data.forecasts);
  const assessments = recordRows(data.assessments);
  const claims = recordRows(data.claims);
  const evidence = recordRows(data.evidence);
  return (
    <section aria-label="Proposal preview" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">Validation and impact preview</h4>
        <StatusIndicator
          status={typeof data.status === "string" ? data.status : "UNAVAILABLE"}
        />
        {typeof data.reason === "string" && (
          <span className="text-xs text-muted-foreground">{data.reason}</span>
        )}
      </div>
      {hasDiffs ? (
        groups.map(([key, title]) => {
          const items = data[key];
          if (!Array.isArray(items)) return null;
          return (
            <details key={key} className="rounded-md border p-3">
              <summary className="cursor-pointer text-sm font-medium">
                {title} ({items.length})
              </summary>
              {items.length === 0 ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  No changes in this section.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {items.map((item, index) => {
                    const row: Record<string, unknown> = isRecord(item)
                      ? item
                      : { value: item };
                    const path =
                      row.path ??
                      row.key ??
                      row.finding_key ??
                      row.claim_key ??
                      "Change";
                    const before = row.previous ?? row.before ?? row.old_value;
                    const after = row.proposed ?? row.after ?? row.new_value;
                    return (
                      <li
                        key={String(path) + ":" + index}
                        className="rounded border p-2 text-xs"
                      >
                        <p className="break-words font-medium">
                          {displayValue(path)}
                        </p>
                        {(before !== undefined || after !== undefined) && (
                          <p className="mt-1 grid gap-1 sm:grid-cols-2">
                            <span>Prior: {displayValue(before)}</span>
                            <span>Proposed: {displayValue(after)}</span>
                          </p>
                        )}
                        {typeof row.reason === "string" && (
                          <p className="mt-1 text-muted-foreground">
                            {row.reason}
                          </p>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </details>
          );
        })
      ) : (
        <p className="rounded-md border p-3 text-sm">
          {typeof data.summary === "string"
            ? data.summary
            : typeof data.baseline_issue === "string"
              ? data.baseline_issue
              : "The domain preview is available; details are retained below."}
        </p>
      )}
      {(forecasts.length > 0 ||
        assessments.length > 0 ||
        claims.length > 0) && (
        <div className="space-y-2 rounded-md border p-3">
          <h5 className="text-sm font-semibold">
            {claims.length > 0
              ? "Proposed thesis revision"
              : "Proposed research observations"}
          </h5>
          {typeof data.contract_type === "string" && (
            <p className="text-xs text-muted-foreground">
              {data.contract_type} · current stream revision{" "}
              {displayValue(data.current_revision_number)} · proposed revision{" "}
              {displayValue(data.candidate_revision_number)}
            </p>
          )}
          {typeof data.contract_type === "string" &&
            [
              "ResearchRevisionContractV1",
              "InvestmentThesisContractV1",
            ].includes(data.contract_type) && (
              <p className="text-xs text-muted-foreground">
                The canonical preview returns the base and proposed content, but
                not the prior revision payload. No field-level delta is
                inferred; use Company Explorer to inspect the accepted history
                before review.
              </p>
            )}
          {typeof data.thesis_statement === "string" && (
            <p className="whitespace-pre-wrap text-sm">
              {data.thesis_statement}
            </p>
          )}
          {forecasts.length > 0 && (
            <div className="space-y-2" aria-label="Proposed agent forecasts">
              <p className="text-xs font-medium text-muted-foreground">
                Agent-authored forecasts are separate from analyst consensus and
                accepted model projections.
              </p>
              {forecasts.map((row, index) => (
                <div
                  key={String(row.metric) + ":" + index}
                  className="rounded border p-2 text-xs"
                >
                  <p className="font-medium">
                    {displayValue(row.metric)} ·{" "}
                    {displayValue(row.fiscal_period)}{" "}
                    {displayValue(row.fiscal_year)} ·{" "}
                    {displayValue(row.scenario)}
                  </p>
                  <p className="mt-1">
                    {displayValue(row.value)} {displayValue(row.currency)} ·{" "}
                    {displayValue(row.unit)} ·{" "}
                    {displayValue(row.availability_status)} · confidence{" "}
                    {displayValue(row.confidence)}
                  </p>
                </div>
              ))}
            </div>
          )}
          {assessments.length > 0 && (
            <ul className="space-y-2">
              {assessments.map((row, index) => (
                <li
                  key={String(row.assessment_type) + ":" + index}
                  className="rounded border p-2 text-xs"
                >
                  <p className="font-medium">
                    {displayValue(row.assessment_type)} ·{" "}
                    {displayValue(row.status)}
                  </p>
                  {typeof row.narrative === "string" && (
                    <p className="mt-1 whitespace-pre-wrap">{row.narrative}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
          {claims.length > 0 && (
            <ul className="space-y-2">
              {claims.map((row, index) => (
                <li
                  key={String(row.claim_key) + ":" + index}
                  className="rounded border p-2 text-xs"
                >
                  <p className="font-medium">
                    {displayValue(row.claim_key)} ·{" "}
                    {displayValue(row.claim_type)} · {displayValue(row.status)}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">
                    {displayValue(row.statement)}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Confidence {displayValue(row.confidence)}
                  </p>
                  {recordRows(row.evidence).map((source, sourceIndex) => (
                    <div
                      key={
                        String(source.external_identifier) + ":" + sourceIndex
                      }
                      className="mt-2 border-t pt-2"
                    >
                      <p>
                        {displayValue(source.source_name)} ·{" "}
                        {displayValue(source.published_at)}
                      </p>
                      {typeof source.excerpt === "string" && (
                        <p className="mt-1">{source.excerpt}</p>
                      )}
                      {typeof source.source_url === "string" && (
                        <SourceReference
                          href={source.source_url}
                          label="Claim evidence"
                        />
                      )}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {evidence.length > 0 && (
        <section
          aria-label="Proposal evidence"
          className="rounded-md border p-3"
        >
          <h5 className="text-sm font-semibold">Supporting evidence</h5>
          <ul className="mt-2 space-y-2">
            {evidence.map((row, index) => (
              <li
                key={String(row.external_identifier) + ":" + index}
                className="rounded border p-2 text-xs"
              >
                <p className="font-medium">
                  {displayValue(row.source_name)} ·{" "}
                  {displayValue(row.published_at)}
                </p>
                {typeof row.excerpt === "string" && (
                  <p className="mt-1">{row.excerpt}</p>
                )}
                {typeof row.note === "string" && (
                  <p className="mt-1 text-muted-foreground">{row.note}</p>
                )}
                {typeof row.source_url === "string" && (
                  <SourceReference
                    href={row.source_url}
                    label="Open supporting source"
                  />
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <details className="rounded-md border p-3">
        <summary className="cursor-pointer text-xs font-medium">
          Full validation record
        </summary>
        <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-[11px]">
          {JSON.stringify(data, null, 2)}
        </pre>
      </details>
    </section>
  );
}

function recordRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}
