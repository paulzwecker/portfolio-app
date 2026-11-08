"use client";

import { useEffect, useRef, useState } from "react";
import { PageSection } from "@/components/app/page-section";
import { PendingOrError } from "@/components/app/empty-state";
import { Button } from "@/components/ui/button";
import { useResearch } from "@/hooks/use-research";
import {
  isLedgerCandidate,
  isLedgerCandidates,
  type LedgerCandidate,
  type LedgerCandidates,
  type LedgerReviewCommand,
  type PortfolioLedgerPreview,
} from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";
import {
  savedLedgerFile,
  downloadLedgerJson,
  ledgerStageBody,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";
import { PortfolioLedgerResults } from "./portfolio-ledger-results";

async function writeCandidate(
  path: string,
  body: string,
  controller: AbortController,
): Promise<LedgerCandidate> {
  const response = await fetch(`/api/research/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
    signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12_000)]),
  });
  if (!response.ok)
    throw new Error(
      response.status === 403
        ? "Server authorization is required before ledger audit records can be written."
        : response.status === 409
          ? "The candidate, source or accepted base changed. Reload history and review the saved packet."
          : "The outcome could not be confirmed. Reload history before another decision. Exact retries are idempotent.",
    );
  const value: unknown = await response.json();
  if (!isLedgerCandidate(value))
    throw new Error(
      "The saved response could not be verified. Reload history.",
    );
  return value;
}

export function PortfolioLedgerCandidates({
  portfolioId,
  sourceReview,
}: {
  portfolioId: string;
  sourceReview: {
    file: LedgerReviewFile;
    report: PortfolioLedgerPreview;
  } | null;
}) {
  const path = `portfolios/${portfolioId}/ledger/candidates`;
  const history = useResearch(path, isLedgerCandidates);
  const verified =
    history.data?.portfolio_id === portfolioId ? history.data : undefined;
  const [selected, setSelected] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  const stage = async () => {
    if (
      !verified ||
      !sourceReview ||
      !reason.trim() ||
      pending ||
      active.current
    )
      return;
    const controller = new AbortController();
    active.current = controller;
    setPending(true);
    setError(null);
    const source = sourceReview;
    const base = verified.current_accepted_candidate_id;
    try {
      const saved = await writeCandidate(
        path,
        ledgerStageBody(
          source.file,
          crypto.randomUUID(),
          base,
          source.report.input_sha256,
          reason.trim(),
        ),
        controller,
      );
      if (controller.signal.aborted) return;
      if (
        saved.portfolio_id !== portfolioId ||
        saved.input_sha256 !== source.report.input_sha256 ||
        saved.base_candidate_id !== base
      )
        throw new Error(
          "The saved candidate does not match the reviewed source and base.",
        );
      setSelected(saved.id);
      history.retry();
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Saving failed. Reload history.",
        );
        history.retry();
      }
    } finally {
      if (active.current === controller) {
        active.current = null;
        setPending(false);
      }
    }
  };
  return (
    <PageSection
      id="ledger-candidates"
      title="Saved candidates and decisions"
      description="Review immutable candidate history. Current holdings use the observed snapshot."
    >
      <div className="space-y-5">
        <p className="rounded-lg border bg-muted/40 p-3 text-sm">
          Saving and decisions create audit records under server authorization.
          Source completeness, account allocation and settled-balance evidence
          require human review.
        </p>
        <Button variant="outline" onClick={history.retry} disabled={pending}>
          Reload candidate history
        </Button>
        {!verified ? (
          <PendingOrError error={history.error} retry={history.retry} />
        ) : (
          <>
            <p className="text-sm">
              {verified.current_revision_number > 0
                ? `Current reviewed revision ${verified.current_revision_number}`
                : "No accepted candidate yet."}
            </p>
            {verified.current_accepted_candidate_id && (
              <Button
                variant="outline"
                onClick={() =>
                  setSelected(verified.current_accepted_candidate_id)
                }
              >
                Open current reviewed candidate
              </Button>
            )}
            {sourceReview && (
              <div className="space-y-3 rounded-lg border p-4">
                <p className="text-sm font-medium">
                  Save validated file · {sourceReview.file.name}
                </p>
                <p className="break-all font-mono text-xs">
                  Input SHA-256 {sourceReview.report.input_sha256}
                </p>
                <label className="block text-sm">
                  Candidate reason
                  <textarea
                    aria-label="Candidate reason"
                    className="mt-1 block min-h-20 w-full rounded-md border bg-background p-2"
                    value={reason}
                    maxLength={1000}
                    disabled={pending}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <Button
                  disabled={!reason.trim() || pending}
                  onClick={() => void stage()}
                >
                  {pending ? "Saving candidate…" : "Save candidate for review"}
                </Button>
              </div>
            )}
            {verified.candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No saved candidates. Validate a private file to prepare one.
              </p>
            ) : (
              <ul
                className="grid gap-2 sm:grid-cols-2"
                aria-label="Ledger candidate history"
              >
                {verified.candidates.map((row) => (
                  <li key={row.id}>
                    <button
                      type="button"
                      aria-pressed={selected === row.id}
                      className="w-full rounded-lg border p-3 text-left text-sm hover:bg-muted/40 aria-pressed:border-primary"
                      onClick={() => setSelected(row.id)}
                    >
                      <span className="font-medium">
                        {row.status}
                        {row.review?.revision_number
                          ? ` · revision ${row.review.revision_number}`
                          : ""}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        Submitted {dateTime(row.submitted_at)} · Cutoff{" "}
                        {dateTime(row.as_of)}
                      </span>
                      <span className="mt-1 block break-words">
                        {row.reason}
                      </span>
                      <span className="block break-all font-mono text-xs">
                        {row.id}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {verified.candidates.length >= 30 && (
              <p className="text-xs">
                Showing the latest 30 candidates. Open the current reviewed
                revision above.
              </p>
            )}
          </>
        )}
        {error && (
          <p role="alert" className="text-sm text-warning">
            {error}
          </p>
        )}
        {selected && (
          <LedgerCandidateDetail
            key={selected}
            portfolioId={portfolioId}
            candidateId={selected}
            history={verified}
            onChanged={history.retry}
            onSelect={setSelected}
          />
        )}
      </div>
    </PageSection>
  );
}

function LedgerCandidateDetail({
  portfolioId,
  candidateId,
  history,
  onChanged,
  onSelect,
}: {
  portfolioId: string;
  candidateId: string;
  history: LedgerCandidates | undefined;
  onChanged: () => void;
  onSelect: (id: string) => void;
}) {
  const path = `portfolios/${portfolioId}/ledger/candidates/${candidateId}`;
  const detail = useResearch(path, isLedgerCandidate);
  const [updated, setUpdated] = useState<LedgerCandidate | null>(null);
  const [reason, setReason] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [decision, setDecision] = useState<"ACCEPT" | "REJECT" | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => () => active.current?.abort(), []);
  const data = updated ?? detail.data;
  const row =
    data?.id === candidateId && data.portfolio_id === portfolioId
      ? data
      : undefined;
  const verifiedId = row?.id;
  useEffect(() => {
    if (verifiedId) heading.current?.focus();
  }, [verifiedId]);
  if (!row) return <PendingOrError error={detail.error} retry={detail.retry} />;
  const file = savedLedgerFile(row.packet);
  const staleBase =
    !history || row.base_candidate_id !== history.current_accepted_candidate_id;
  const approvals = [
    [
      "source",
      "I reviewed the original source documents and complete period coverage.",
    ],
    [
      "accounts",
      "I verified account allocation and exact security/listing identities.",
    ],
    [
      "settled",
      "I verified the settled-balance basis and opening/ending observations.",
    ],
    [
      "replacement",
      "I reviewed the complete replacement packet and opening-account changes.",
    ],
    ...row.changes.changed_activity_ids.map((id) => [
      `changed-${id}`,
      `I reviewed changed activity ${id}.`,
    ]),
    ...row.changes.removed_activity_ids.map((id) => [
      `removed-${id}`,
      `I approve excluding activity ${id} from this replacement.`,
    ]),
  ];
  const canAccept =
    row.status === "PENDING" &&
    row.preview_status === "ENDING_RECONCILED" &&
    !staleBase;
  const ready =
    Boolean(reason.trim()) &&
    (decision === "REJECT" ||
      (canAccept && approvals.every(([key]) => checks[key])));
  const review = async () => {
    if (!decision || !ready || pending || active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setPending(true);
    setError(null);
    const common = {
      expected_base_candidate_id: row.base_candidate_id,
      expected_input_sha256: row.input_sha256,
      expected_preview_sha256: row.preview_sha256,
      reason: reason.trim(),
    };
    const command: LedgerReviewCommand =
      decision === "REJECT"
        ? { ...common, decision: "REJECT" }
        : {
            ...common,
            decision: "ACCEPT",
            source_evidence_reviewed: true,
            account_allocation_reviewed: true,
            settled_balance_basis_reviewed: true,
            full_replacement_reviewed: true,
            acknowledged_changed_activity_ids: row.changes.changed_activity_ids,
            acknowledged_removed_activity_ids: row.changes.removed_activity_ids,
          };
    try {
      const result = await writeCandidate(
        `${path}/review`,
        JSON.stringify(command),
        controller,
      );
      if (controller.signal.aborted) return;
      if (
        result.id !== row.id ||
        result.portfolio_id !== portfolioId ||
        result.input_sha256 !== row.input_sha256 ||
        result.preview_sha256 !== row.preview_sha256 ||
        result.review?.decision !== decision
      )
        throw new Error(
          "The receipt does not match the explicit decision. Reload history.",
        );
      setUpdated(result);
      setDecision(null);
      setChecks({});
      onChanged();
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Outcome unknown. Reload history.",
        );
        setDecision(null);
        setChecks({});
        onChanged();
        detail.retry();
      }
    } finally {
      if (active.current === controller) {
        active.current = null;
        setPending(false);
      }
    }
  };
  return (
    <article
      className="space-y-5 rounded-xl border p-4 sm:p-6"
      aria-label="Saved ledger candidate"
    >
      <h3 ref={heading} tabIndex={-1} className="text-lg font-semibold">
        {row.status} candidate {row.id.slice(0, 8)}
      </h3>
      <Button
        variant="outline"
        disabled={pending}
        onClick={() => {
          setUpdated(null);
          setDecision(null);
          setChecks({});
          detail.retry();
          onChanged();
        }}
      >
        Reload saved candidate
      </Button>
      <p className="text-sm">
        Cutoff {dateTime(row.as_of)} · Submitted {dateTime(row.submitted_at)}
      </p>
      <details className="rounded-lg border p-3 text-sm">
        <summary className="cursor-pointer font-medium">
          Candidate hashes and revision base
        </summary>
        <dl className="mt-3 space-y-2 break-all text-xs">
          {[
            ["Candidate", row.id],
            ["Input SHA-256", row.input_sha256],
            ["Packet SHA-256", row.packet_sha256],
            ["Preview SHA-256", row.preview_sha256],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="font-medium">{label}</dt>
              <dd className="font-mono">{value}</dd>
            </div>
          ))}
          <div>
            <dt>Base candidate</dt>
            <dd>
              {row.base_candidate_id ? (
                <button
                  type="button"
                  className="underline"
                  onClick={() => onSelect(row.base_candidate_id!)}
                >
                  {row.base_candidate_id}
                </button>
              ) : (
                "First reviewed revision"
              )}
            </dd>
          </div>
        </dl>
      </details>
      <div
        className="rounded-lg bg-muted/40 p-3 text-sm"
        aria-label="Replacement scope"
      >
        <p>
          {row.changes.added_activity_ids.length} added ·{" "}
          {row.changes.changed_activity_ids.length} changed ·{" "}
          {row.changes.removed_activity_ids.length} removed activity records
        </p>
        <p>
          Opening accounts{" "}
          {row.base_candidate_id === null
            ? "require initial source review"
            : row.changes.opening_changed
              ? "changed and require review"
              : "match the revision base"}
        </p>
        <ul className="mt-2 break-all font-mono text-xs">
          {row.changes.changed_activity_ids.map((id) => (
            <li key={id}>Changed {id}</li>
          ))}
          {row.changes.removed_activity_ids.map((id) => (
            <li key={id}>Removed {id}</li>
          ))}
        </ul>
      </div>
      <Button
        variant="outline"
        onClick={() => downloadLedgerJson(row, "private-ledger-candidate.json")}
      >
        Download private candidate and receipt
      </Button>
      <details className="rounded-lg border p-3 text-sm">
        <summary className="cursor-pointer font-medium">
          Opening account allocation
        </summary>
        <ul className="mt-3 space-y-2">
          {row.packet.accounts.map((account) => (
            <li key={account.account_id} className="break-words">
              {account.name} · {account.kind} ·{" "}
              {account.broker_name ?? "Unallocated opening"}
              <p className="break-all font-mono text-xs">
                {account.account_id}
              </p>
            </li>
          ))}
        </ul>
      </details>
      <details className="rounded-lg border p-3 text-sm">
        <summary className="cursor-pointer font-medium">
          Saved activity records ({row.packet.activity.length})
        </summary>
        <ul className="mt-3 space-y-4">
          {row.packet.activity.map((item) => (
            <li key={item.id} className="rounded-lg bg-muted/40 p-3">
              <p className="font-medium">
                {item.kind} · {dateTime(item.effective_at)}
              </p>
              <p className="break-all font-mono text-xs">{item.id}</p>
              {"gross_cash" in item ? (
                <p className="mt-1 break-words">
                  Quantity {item.quantity} · Listing {item.listing_id} · Gross{" "}
                  {item.gross_cash} {item.currency} · Fees {item.fees} · Taxes{" "}
                  {item.taxes} · Trade {item.trade_date} · Settlement{" "}
                  {item.settlement_date}
                </p>
              ) : (
                <p>
                  Amount {item.amount} {item.currency}
                </p>
              )}
              <p className="mt-1 break-words">
                Source record {item.evidence.source_record_id}
              </p>
              <p className="break-all font-mono text-xs">
                {item.evidence.source_sha256}
              </p>
            </li>
          ))}
        </ul>
      </details>
      <PortfolioLedgerResults report={row.preview} file={file} />
      {row.review ? (
        <div
          className="rounded-lg border p-4 text-sm"
          role="status"
          aria-label="Ledger decision receipt"
        >
          <p>
            {row.review.decision === "ACCEPT"
              ? `Reviewed revision ${row.review.revision_number}`
              : "Rejected candidate"}{" "}
            · {dateTime(row.review.reviewed_at)} · {row.review.reviewed_by}
          </p>
          <p className="mt-2 break-words">{row.review.command.reason}</p>
          <p className="mt-2 break-all font-mono text-xs">
            Receipt {row.review.id}
          </p>
        </div>
      ) : (
        <div className="space-y-4 rounded-lg border p-4">
          <p className="text-sm">
            Acceptance records reviewed candidate history. Portfolio ownership
            cutover requires its separate approved workflow.
          </p>
          {staleBase && (
            <p className="text-sm text-warning">
              The accepted base changed or history is unavailable. Reload
              history and stage a new candidate before acceptance.
            </p>
          )}
          {row.preview_status !== "ENDING_RECONCILED" && (
            <p className="text-sm text-warning">
              Acceptance requires matching opening and ending evidence.
            </p>
          )}
          <label className="block text-sm">
            Decision rationale
            <textarea
              aria-label="Decision rationale"
              className="mt-1 block min-h-20 w-full rounded-md border bg-background p-2"
              value={reason}
              disabled={pending}
              maxLength={1000}
              onChange={(e) => {
                setReason(e.target.value);
                setDecision(null);
              }}
            />
          </label>
          <fieldset className="space-y-3" disabled={pending}>
            <legend className="mb-2 text-sm font-medium">
              Acceptance evidence
            </legend>
            {approvals.map(([key, label]) => (
              <label
                key={key}
                className="flex min-h-10 items-start gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  checked={Boolean(checks[key])}
                  className="mt-1 shrink-0"
                  onChange={(e) => {
                    setChecks((current) => ({
                      ...current,
                      [key]: e.target.checked,
                    }));
                    setDecision(null);
                  }}
                />
                <span className="min-w-0 break-words">{label}</span>
              </label>
            ))}
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={
                !canAccept ||
                !reason.trim() ||
                !approvals.every(([key]) => checks[key]) ||
                pending
              }
              onClick={() => setDecision("ACCEPT")}
            >
              Review acceptance
            </Button>
            <Button
              variant="outline"
              disabled={!reason.trim() || pending}
              onClick={() => setDecision("REJECT")}
            >
              Review rejection
            </Button>
          </div>
          {decision && (
            <div
              className="space-y-3 rounded-lg border border-warning/40 p-3"
              role="group"
              aria-label="Confirm ledger decision"
            >
              <p className="text-sm">
                Confirm{" "}
                {decision === "ACCEPT"
                  ? "acceptance of this exact saved candidate"
                  : "rejection of this candidate"}{" "}
                with input SHA-256{" "}
                <span className="break-all font-mono text-xs">
                  {row.input_sha256}
                </span>
                .
              </p>
              <p className="break-words text-sm">{reason.trim()}</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={!ready || pending}
                  onClick={() => void review()}
                >
                  {pending
                    ? "Recording decision…"
                    : `Confirm ${decision === "ACCEPT" ? "acceptance" : "rejection"}`}
                </Button>
                <Button
                  variant="ghost"
                  disabled={pending}
                  onClick={() => setDecision(null)}
                >
                  Cancel decision
                </Button>
              </div>
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-warning">
              {error}
            </p>
          )}
        </div>
      )}
    </article>
  );
}
