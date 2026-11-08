"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useResearch } from "@/hooks/use-research";
import { dateTime } from "@/lib/display";
import type { LedgerCandidate } from "@/lib/domain-contracts";
import {
  isLedgerOwnership,
  isLedgerPublication,
  isLedgerPublicationPlan,
  publicationMatchesCandidate,
  type LedgerPublication,
  type LedgerPublicationCommand,
  type LedgerPublicationPlan,
} from "@/lib/ledger-publication-contracts";
import { downloadLedgerJson } from "./portfolio-ledger-data";

const acknowledgements = [
  [
    "ownership_transfer_reviewed",
    "I approve transferring holdings authority to the accepted ledger. Manual snapshots and full workbook apply will be blocked.",
  ],
  [
    "whole_portfolio_scope_reviewed",
    "I reviewed every account and the entire portfolio replacement, including cash in each original currency.",
  ],
  [
    "current_state_recovery_verified",
    "I independently verified an authorized recovery point containing the current accepted holdings and its recovery procedure.",
  ],
  [
    "holdings_confirmation",
    "I confirm the exact proposed quantities, listing identities, native cash and evidenced closing cutoff.",
  ],
] as const;

export function PortfolioLedgerPublication({
  candidate,
  currentCandidateId,
}: {
  candidate: LedgerCandidate;
  currentCandidateId: string | null | undefined;
}) {
  const [opened, setOpened] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<LedgerPublication | null>(null);
  const path = `portfolios/${candidate.portfolio_id}/ledger`;
  const preview = useResearch(
    `${path}/candidates/${candidate.id}/publication-preview`,
    isLedgerPublicationPlan,
    0,
    opened,
  );
  const ownership = useResearch(
    `${path}/ownership`,
    isLedgerOwnership,
    0,
    opened,
  );
  const plan =
    preview.data && publicationMatchesCandidate(preview.data, candidate)
      ? preview.data
      : undefined;
  const owner =
    ownership.data?.portfolio_id === candidate.portfolio_id
      ? ownership.data
      : undefined;
  const recorded = owner?.latest_publication;
  const verifiedReceipt =
    receipt ?? (recorded?.candidate_id === candidate.id ? recorded : null);
  const reload = () => {
    preview.retry();
    ownership.retry();
  };
  const result = (value: LedgerPublication | null, message: string) => {
    setReceipt(value);
    setNotice(message);
    reload();
    if (value) window.dispatchEvent(new Event("portfolio:data-refreshed"));
  };
  return (
    <section
      className="space-y-4 rounded-xl border border-primary/30 p-4"
      aria-label="Holdings publication"
    >
      <h4 className="text-base font-semibold">Publish reviewed holdings</h4>
      <p className="text-sm">
        Publish a complete canonical holdings snapshot from this accepted ledger
        revision. Its closing-statement time becomes the effective cutoff.
        Strategic targets retain their independent revision.
      </p>
      {!opened ? (
        <Button variant="outline" onClick={() => setOpened(true)}>
          Load read-only publication plan
        </Button>
      ) : (
        <>
          <Button
            variant="outline"
            onClick={() => {
              setNotice(null);
              setReceipt(null);
              reload();
            }}
          >
            Reload publication state
          </Button>
          {notice && (
            <p role="status" className="break-words text-sm">
              {notice}
            </p>
          )}
          {preview.error ||
          ownership.error ||
          (preview.data && !plan) ||
          (ownership.data && !owner) ? (
            <p role="alert" className="text-sm text-warning">
              Publication state could not be verified. This requires a current
              accepted candidate, unchanged evidence and a strictly later
              closing cutoff. Reload after checking the API and required
              migrations.
            </p>
          ) : !plan || !owner ? (
            <p role="status" className="text-sm">
              Verifying publication plan and holdings authority…
            </p>
          ) : (
            <>
              <p className="text-sm">
                Current authority{" "}
                {owner.source === "ACCEPTED_LEDGER"
                  ? "accepted ledger"
                  : "observed holdings snapshot"}{" "}
                · Whole portfolio
              </p>
              <PublicationPlan
                key={`${plan.plan_sha256}/${plan.status}/${plan.publication_id}`}
                plan={plan}
                candidate={candidate}
                enabled={
                  currentCandidateId === candidate.id &&
                  (owner.latest_publication?.id ?? null) ===
                    plan.previous_publication_id
                }
                onResult={result}
              />
            </>
          )}
          {verifiedReceipt && (
            <div
              role="status"
              aria-label="Holdings publication receipt"
              className="space-y-2 rounded-lg bg-muted/40 p-3 text-sm"
            >
              <p>
                Published revision {verifiedReceipt.plan.review_revision_number}{" "}
                · {dateTime(verifiedReceipt.published_at)} ·{" "}
                {verifiedReceipt.published_by}
              </p>
              <p className="break-all font-mono text-xs">
                Publication {verifiedReceipt.id}
              </p>
              <p className="break-all font-mono text-xs">
                Snapshot {verifiedReceipt.snapshot.id} · SHA-256{" "}
                {verifiedReceipt.snapshot_sha256}
              </p>
              <Button
                variant="outline"
                onClick={() =>
                  downloadLedgerJson(
                    verifiedReceipt,
                    "private-ledger-publication.json",
                  )
                }
              >
                Download private publication receipt
              </Button>
              <Link href="/portfolio" className="block underline">
                View canonical Portfolio holdings
              </Link>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function PublicationPlan({
  plan,
  candidate,
  enabled,
  onResult,
}: {
  plan: LedgerPublicationPlan;
  candidate: LedgerCandidate;
  enabled: boolean;
  onResult: (receipt: LedgerPublication | null, message: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const active = useRef<AbortController | null>(null);
  const confirmationHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => {
    if (confirming) confirmationHeading.current?.focus();
  }, [confirming]);
  const ready =
    enabled &&
    plan.status === "READY" &&
    reason.trim().length > 0 &&
    typed === plan.confirmation_phrase &&
    acknowledgements.every(([key]) => checks[key]);
  const publish = async () => {
    if (!ready || !confirming || pending || active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setPending(true);
    const command: LedgerPublicationCommand = {
      expected_plan_sha256: plan.plan_sha256,
      expected_previous_publication_id: plan.previous_publication_id,
      confirmation: typed,
      reason: reason.trim(),
      ownership_transfer_reviewed: true,
      whole_portfolio_scope_reviewed: true,
      current_state_recovery_verified: true,
      holdings_confirmation: true,
    };
    try {
      const response = await fetch(
        `/api/research/portfolios/${plan.portfolio_id}/ledger/candidates/${plan.candidate_id}/publish`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(command),
          cache: "no-store",
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(12_000),
          ]),
        },
      );
      if (!response.ok)
        throw new Error(
          response.status === 403
            ? "Server-side owner authorization is required. Approval checks have been cleared."
            : response.status === 409
              ? "The plan, source or holdings authority changed. Review a fresh plan before any further action."
              : "Publication outcome is unknown. Read-only state is being reloaded. Check for a receipt before another attempt.",
        );
      const value: unknown = await response.json();
      if (
        !isLedgerPublication(value) ||
        !publicationMatchesCandidate(value.plan, candidate) ||
        value.plan.plan_sha256 !== plan.plan_sha256 ||
        Object.entries(command).some(
          ([key, expected]) =>
            value.command[key as keyof LedgerPublicationCommand] !== expected,
        )
      )
        throw new Error(
          "The publication response could not be verified. Check read-only state for a receipt before another attempt.",
        );
      if (!controller.signal.aborted)
        onResult(
          value,
          "Publication verified. Canonical holdings and immutable ownership receipt were recorded.",
        );
    } catch (error) {
      if (!controller.signal.aborted)
        onResult(
          null,
          error instanceof Error
            ? error.message
            : "Publication outcome is unknown. Check read-only state before another attempt.",
        );
    } finally {
      if (active.current === controller) {
        active.current = null;
        setPending(false);
      }
    }
  };
  const listingLabel = (id: string) => {
    const listing = candidate.preview.consumed_listings.find(
      (row) => row.listing_id === id,
    );
    return listing
      ? `${listing.venue}:${listing.ticker} · ${listing.currency} · ${listing.security_type}`
      : id;
  };
  return (
    <div className="space-y-4">
      <p className="text-sm">
        Holdings effective {dateTime(plan.effective_at)} · Ownership cutover{" "}
        {dateTime(plan.cutover_at)}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {[
          {
            title: "Current canonical holdings",
            positions: plan.current_snapshot.positions,
            cash: plan.current_snapshot.cash_positions,
          },
          {
            title: "Proposed complete replacement",
            positions: plan.positions,
            cash: plan.cash,
          },
        ].map((group) => (
          <div
            key={group.title}
            className="rounded-lg border p-3"
            aria-label={group.title}
          >
            <h5 className="font-medium">{group.title}</h5>
            <ul className="mt-2 space-y-2 text-sm">
              {group.positions.map((row) => (
                <li key={row.listing_id}>
                  <p className="break-words">{listingLabel(row.listing_id)}</p>
                  <p className="break-all font-mono text-xs">
                    {row.listing_id}
                  </p>
                  <p className="break-all">
                    Quantity {row.quantity ?? "Unavailable"}
                  </p>
                </li>
              ))}
            </ul>
            <ul
              className="mt-3 space-y-1 text-sm"
              aria-label={`${group.title} cash`}
            >
              {group.cash.map((row) => (
                <li key={row.currency} className="break-all">
                  {row.currency} {row.balance ?? "Unavailable"}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <details className="rounded-lg border p-3 text-xs">
        <summary className="cursor-pointer font-medium">
          Publication identity and source hashes
        </summary>
        <dl className="mt-3 space-y-2 break-all font-mono">
          {[
            ["Plan SHA-256", plan.plan_sha256],
            ["Candidate input SHA-256", plan.candidate_input_sha256],
            ["Candidate preview SHA-256", plan.candidate_preview_sha256],
            ["Opening snapshot", plan.anchor_snapshot_id],
            ["Opening SHA-256", plan.anchor_sha256],
            ["Current snapshot", plan.current_snapshot.id],
            ["Current snapshot SHA-256", plan.current_snapshot_sha256],
            [
              "Previous publication",
              plan.previous_publication_id ?? "First publication",
            ],
            ["Included accounts", plan.account_ids.join(", ")],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="font-sans font-medium">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </details>
      <Button
        variant="outline"
        onClick={() =>
          downloadLedgerJson(plan, "private-ledger-publication-plan.json")
        }
      >
        Download private publication plan
      </Button>
      {plan.status === "ALREADY_PUBLISHED" ? (
        <p role="status" className="break-all text-sm">
          Already published · {plan.publication_id}. This historical plan
          records the state before that publication.
        </p>
      ) : (
        <>
          {!enabled && (
            <p role="alert" className="text-sm text-warning">
              The accepted revision or holdings authority differs from this
              plan. Reload state and review the current candidate.
            </p>
          )}
          <p className="text-sm">
            Publication transfers the whole portfolio to ledger authority. Full
            workbook apply and manual snapshot entry become blocked. Verify a
            recovery point containing the current accepted holdings before
            confirming.
          </p>
          <fieldset className="space-y-3" disabled={pending || !enabled}>
            <legend className="mb-2 font-medium">
              Publication authorization
            </legend>
            <label className="block text-sm">
              Publication rationale
              <textarea
                aria-label="Publication rationale"
                value={reason}
                maxLength={1000}
                className="mt-1 block min-h-20 w-full rounded-md border bg-background p-2"
                onChange={(e) => {
                  setReason(e.target.value);
                  setConfirming(false);
                }}
              />
            </label>
            {acknowledgements.map(([key, label]) => (
              <label
                key={key}
                className="flex min-h-11 items-start gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  className="mt-1 shrink-0"
                  checked={Boolean(checks[key])}
                  onChange={(e) => {
                    setChecks((previous) => ({
                      ...previous,
                      [key]: e.target.checked,
                    }));
                    setConfirming(false);
                  }}
                />
                <span className="min-w-0 break-words">{label}</span>
              </label>
            ))}
            <label className="block text-sm">
              Type the exact publication confirmation
              <span className="my-2 block select-all break-all font-mono text-xs">
                {plan.confirmation_phrase}
              </span>
              <textarea
                aria-label="Typed publication confirmation"
                autoComplete="off"
                spellCheck={false}
                value={typed}
                className="block min-h-24 w-full rounded-md border bg-background p-2 font-mono text-xs"
                onChange={(e) => {
                  setTyped(e.target.value);
                  setConfirming(false);
                }}
              />
            </label>
          </fieldset>
          <Button
            disabled={!ready || pending}
            onClick={() => setConfirming(true)}
          >
            Review holdings publication
          </Button>
          {confirming && (
            <div
              role="group"
              aria-label="Confirm holdings publication"
              className="space-y-3 rounded-lg border border-warning/40 p-3"
            >
              <h5
                ref={confirmationHeading}
                tabIndex={-1}
                className="font-medium"
              >
                Confirm whole-portfolio publication
              </h5>
              <p className="text-sm">
                Publish accepted revision {plan.review_revision_number} at{" "}
                {dateTime(plan.effective_at)}.
              </p>
              <p className="break-all font-mono text-xs">
                Plan {plan.plan_sha256}
              </p>
              <p className="break-words text-sm">{reason.trim()}</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={!ready || pending}
                  onClick={() => void publish()}
                >
                  {pending
                    ? "Publishing holdings…"
                    : "Confirm holdings publication"}
                </Button>
                <Button
                  variant="ghost"
                  disabled={pending}
                  onClick={() => setConfirming(false)}
                >
                  Cancel publication
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
