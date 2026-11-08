"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/app/page-header";
import { PageSection } from "@/components/app/page-section";
import { PendingOrError } from "@/components/app/empty-state";
import { Button } from "@/components/ui/button";
import { useResearch } from "@/hooks/use-research";
import {
  isPortfolioLedgerAnchor,
  isPortfolioLedgerPreview,
  type PortfolioLedgerPreview,
} from "@/lib/domain-contracts";
import { dateTime } from "@/lib/display";
import {
  downloadLedgerJson,
  inspectLedgerFile,
  ledgerSameInstant,
  ledgerFileLimit,
  type LedgerReviewFile,
} from "./portfolio-ledger-data";
import { PortfolioLedgerCandidates } from "./portfolio-ledger-candidates";
import { PortfolioLedgerResults } from "./portfolio-ledger-results";
import { LedgerOpeningBuilder } from "./ledger-opening-builder";
import { LedgerSettledActivityBuilder } from "./ledger-settled-activity-builder";
import {
  restoreSettledActivityReview,
  type SettledActivitySession,
} from "./ledger-settled-activity";
import { LedgerEndingBuilder } from "./ledger-ending-builder";
import {
  endingOpeningAccounts,
  restoreEndingReview,
  type EndingAccountDraft,
} from "./ledger-ending-draft";
import type { OpeningAccountDraft } from "./ledger-opening-draft";

function matchesReviewSource(
  opening: OpeningAccountDraft[],
  file: LedgerReviewFile,
  report: PortfolioLedgerPreview,
): boolean {
  const activity: unknown = JSON.parse(file.text).activity;
  const accounts = new Set(
    report.accounts.map((account) => account.account_id.toLowerCase()),
  );
  return (
    Array.isArray(activity) &&
    activity.length === report.activity_count &&
    report.accounts.length === opening.length &&
    accounts.size === opening.length &&
    opening.every((account) => accounts.has(account.id.toLowerCase()))
  );
}

export function PortfolioLedgerWorkspace({
  portfolioId,
  portfolioName,
}: {
  portfolioId: string;
  portfolioName: string;
}) {
  const anchor = useResearch(
    `portfolios/${portfolioId}/ledger/anchor`,
    isPortfolioLedgerAnchor,
  );
  const verified =
    anchor.data?.portfolio_id === portfolioId ? anchor.data : undefined;
  const [file, setFile] = useState<LedgerReviewFile | null>(null);
  const [activityBase, setActivityBase] =
    useState<SettledActivitySession | null>(null);
  const [endingBase, setEndingBase] = useState<{
    file: LedgerReviewFile;
    opening: OpeningAccountDraft[];
    initialAccounts?: EndingAccountDraft[];
    cancelFile?: LedgerReviewFile;
  } | null>(null);
  const [review, setReview] = useState<{
    report: PortfolioLedgerPreview;
    file: LedgerReviewFile;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const [pending, setPending] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const fileVersion = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      fileVersion.current += 1;
      activeRequest.current?.abort();
    },
    [],
  );

  const matchesAnchor = Boolean(
    file &&
    verified &&
    file.anchorSnapshotId === verified.snapshot.id &&
    file.anchorSha256 === verified.anchor_sha256,
  );
  const visibleReview =
    review &&
    review.file === file &&
    review.report.anchor_sha256 === verified?.anchor_sha256
      ? review
      : null;

  const loadFile = async (selected: File | undefined) => {
    setActivityBase(null);
    setEndingBase(null);
    const version = ++fileVersion.current;
    activeRequest.current?.abort();
    activeRequest.current = null;
    setFile(null);
    setReview(null);
    setError(null);
    setPending(false);
    if (!selected) {
      setLoadingFile(false);
      return;
    }
    setLoadingFile(true);
    try {
      if (selected.size > ledgerFileLimit)
        throw new Error("Choose a ledger review JSON file smaller than 1 MB.");
      const text = new TextDecoder("utf-8", { fatal: true }).decode(
        await selected.arrayBuffer(),
      );
      const candidate = inspectLedgerFile(text, selected.name);
      if (version === fileVersion.current) setFile(candidate);
    } catch (failure) {
      if (version === fileVersion.current)
        setError(
          failure instanceof Error && failure.name !== "TypeError"
            ? failure.message
            : "The file must contain valid UTF-8 ledger JSON.",
        );
    } finally {
      if (version === fileVersion.current) setLoadingFile(false);
    }
  };

  const runPreview = async (candidate = file) => {
    if (
      !candidate ||
      !verified ||
      candidate.anchorSnapshotId !== verified.snapshot.id ||
      candidate.anchorSha256 !== verified.anchor_sha256 ||
      pending
    )
      return;
    const controller = new AbortController();
    activeRequest.current?.abort();
    activeRequest.current = controller;
    fileVersion.current += 1;
    if (input.current) input.current.value = "";
    setFile(candidate);
    setPending(true);
    setError(null);
    setReview(null);
    try {
      const response = await fetch(
        `/api/research/portfolios/${portfolioId}/ledger/preview`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          cache: "no-store",
          // Re-serializing parsed JSON could round numeric source literals in JavaScript.
          body: candidate.text,
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(12_000),
          ]),
        },
      );
      const data: unknown = await response.json();
      if (controller.signal.aborted || activeRequest.current !== controller)
        return;
      if (!response.ok)
        throw new Error(
          response.status === 409
            ? "The current anchor changed. Reload it and review the source file before retrying."
            : response.status === 422
              ? "Check the ledger source contract, exact identities, dates and complete observations."
              : "Ledger validation is unavailable. Check the API and retry.",
        );
      if (
        !isPortfolioLedgerPreview(data) ||
        data.portfolio_id !== portfolioId ||
        data.anchor_snapshot_id !== candidate.anchorSnapshotId ||
        data.anchor_sha256 !== candidate.anchorSha256 ||
        !ledgerSameInstant(data.as_of, candidate.asOf) ||
        (data.ending_statement_at != null &&
          !ledgerSameInstant(data.ending_statement_at, data.as_of))
      )
        throw new Error(
          "The ledger result could not be verified against this file and portfolio.",
        );
      setReview({ report: data, file: candidate });
    } catch (failure) {
      if (!controller.signal.aborted && activeRequest.current === controller)
        setError(
          failure instanceof Error
            ? failure.message
            : "Ledger validation is unavailable.",
        );
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setPending(false);
      }
    }
  };

  const clear = (retainActivity = false, retainEnding = false) => {
    if (!retainActivity) setActivityBase(null);
    if (!retainEnding) setEndingBase(null);
    fileVersion.current += 1;
    activeRequest.current?.abort();
    activeRequest.current = null;
    setFile(null);
    setReview(null);
    setError(null);
    setPending(false);
    setLoadingFile(false);
    if (input.current) input.current.value = "";
  };

  return (
    <div className="space-y-7">
      <Link className="text-sm underline underline-offset-4" href="/portfolio">
        Back to portfolio
      </Link>
      <PageHeader
        eyebrow={portfolioName}
        title="Transaction ledger review"
        description="Compare a private candidate ledger with observed holdings and ending statements. Review exact positions, currency cash and source evidence."
        actions={
          <Button
            variant="outline"
            disabled={
              Boolean(activityBase || endingBase) || pending || loadingFile
            }
            onClick={() => {
              activeRequest.current?.abort();
              activeRequest.current = null;
              setPending(false);
              setReview(null);
              setActivityBase(null);
              setEndingBase(null);
              anchor.retry();
            }}
          >
            Reload observed anchor
          </Button>
        }
      />
      <p className="rounded-lg border bg-muted/40 p-4 text-sm">
        Source-bound candidate review. Canonical holdings and strategic targets
        retain authority. Account allocation, source completeness and any future
        cutover require explicit review.
      </p>
      {!verified ? (
        <PendingOrError error={anchor.error} retry={anchor.retry} />
      ) : (
        <>
          <PageSection
            title="1. Verify the opening anchor"
            description="Use this exact snapshot ID and SHA-256 in the private ledger file."
          >
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4 text-sm">
              <div>
                <p>
                  Observed holdings · {dateTime(verified.snapshot.effective_at)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Recorded {dateTime(verified.snapshot.recorded_at)} ·{" "}
                  {verified.snapshot.positions.length} listing rows ·{" "}
                  {verified.snapshot.cash_positions.length} cash rows
                </p>
              </div>
              <Button
                variant="outline"
                onClick={() =>
                  downloadLedgerJson(verified, "ledger-anchor.json")
                }
              >
                Download private anchor
              </Button>
            </div>
          </PageSection>
          <PageSection
            title="2. Review opening balances"
            description="Enter source-evidenced accounts and exact balances. The API checks the combined opening against this observed snapshot."
          >
            <LedgerOpeningBuilder
              key={verified.anchor_sha256}
              anchor={verified}
              disabled={
                pending || loadingFile || Boolean(activityBase || endingBase)
              }
              collapsed={Boolean(activityBase || endingBase)}
              onChange={() => clear()}
              onReview={runPreview}
            />
          </PageSection>
          {activityBase &&
            activityBase.base.anchorSha256 === verified.anchor_sha256 && (
              <PageSection
                title="Settled activity"
                description="Build a candidate from the reconciled opening and your transaction evidence."
              >
                <LedgerSettledActivityBuilder
                  key={activityBase.base.text}
                  anchor={verified}
                  base={activityBase.base}
                  initialCutoff={activityBase.cutoff}
                  initialEntries={activityBase.entries}
                  disabled={pending || loadingFile}
                  onChange={() => clear(true)}
                  onReview={runPreview}
                  onClose={() => clear()}
                />
              </PageSection>
            )}
          {endingBase &&
            endingBase.file.anchorSha256 === verified.anchor_sha256 && (
              <PageSection
                title="Ending statement"
                description="Enter independent observations for each opening account at the review cutoff."
              >
                <LedgerEndingBuilder
                  key={endingBase.file.text}
                  anchor={verified}
                  base={endingBase.file}
                  opening={endingBase.opening}
                  initialAccounts={endingBase.initialAccounts}
                  disabled={pending || loadingFile}
                  onChange={() => clear(false, true)}
                  onReview={runPreview}
                  onClose={() => {
                    const previous = endingBase.cancelFile ?? endingBase.file;
                    clear();
                    setFile(previous);
                  }}
                />
              </PageSection>
            )}
          <PageSection
            title="3. Validate a private ledger file"
            description="Choose a UTF-8 portfolio-ledger-preview-v1 or v2 JSON file containing evidenced accounts, opening balances, activity and optional ending observations. Use v2 for observed income and paired internal cash or same-listing security transfers. Maximum 1 MB."
          >
            <label
              className="block text-sm font-medium"
              htmlFor="ledger-review-file"
            >
              Ledger review JSON
              <input
                id="ledger-review-file"
                ref={input}
                type="file"
                accept=".json,application/json"
                disabled={Boolean(activityBase || endingBase)}
                onChange={(event) => void loadFile(event.target.files?.[0])}
                className="mt-2 block w-full min-w-0 rounded-md border bg-background p-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-muted file:px-3 file:py-2 file:text-foreground"
              />
            </label>
            <p className="mt-2 text-xs text-muted-foreground">
              Selecting a file keeps its contents in this page. Validation sends
              the exact text to the authenticated application API.
            </p>
            {file && (
              <p className="mt-3 break-words text-sm">
                {file.name} · Booking cutoff {dateTime(file.asOf)}
              </p>
            )}
            {file && !matchesAnchor && (
              <p role="alert" className="mt-3 text-sm text-warning">
                This file belongs to a different or stale anchor. Review its
                snapshot ID/hash before validation.
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                disabled={
                  !file ||
                  !matchesAnchor ||
                  pending ||
                  loadingFile ||
                  Boolean(activityBase || endingBase)
                }
                onClick={() => void runPreview()}
              >
                {pending
                  ? "Validating ledger…"
                  : loadingFile
                    ? "Reading private file…"
                    : "Validate and reconcile"}
              </Button>
              <Button
                variant="ghost"
                onClick={() => clear()}
                disabled={
                  Boolean(activityBase || endingBase) ||
                  (!file && !error && !pending && !loadingFile)
                }
              >
                Clear private file
              </Button>
            </div>
          </PageSection>
        </>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-lg border border-warning/40 p-3 text-sm text-warning"
        >
          {error}
        </p>
      )}
      <a href="#ledger-candidates" className="inline-block text-sm underline">
        Open saved candidates and decisions
      </a>
      {visibleReview && (
        <>
          {visibleReview.report.status === "OPENING_RECONCILED" &&
            visibleReview.report.activity_count === 0 &&
            visibleReview.file.name === "opening-balances.json" &&
            !activityBase &&
            !endingBase && (
              <Button
                variant="outline"
                onClick={() =>
                  setActivityBase({
                    base: visibleReview.file,
                    cutoff: "",
                    entries: [],
                  })
                }
              >
                Add settled activity
              </Button>
            )}
          {verified &&
            visibleReview.report.status === "OPENING_RECONCILED" &&
            visibleReview.report.activity_count > 0 &&
            visibleReview.report.ending_status === "NOT_PROVIDED" &&
            !activityBase &&
            !endingBase && (
              <Button
                variant="outline"
                onClick={() => {
                  try {
                    const session = restoreSettledActivityReview(
                      verified,
                      visibleReview.file.text,
                    );
                    if (
                      session.entries.length !==
                      visibleReview.report.activity_count
                    )
                      throw new Error("The review activity count changed.");
                    setError(null);
                    setActivityBase(session);
                  } catch (failure) {
                    setError(
                      failure instanceof Error
                        ? failure.message
                        : "This review cannot be edited in the settled activity form.",
                    );
                  }
                }}
              >
                Edit supported activity
              </Button>
            )}
          {verified &&
            visibleReview.report.status === "OPENING_RECONCILED" &&
            visibleReview.report.ending_status === "NOT_PROVIDED" &&
            !endingBase && (
              <Button
                variant="outline"
                onClick={() => {
                  try {
                    const opening = endingOpeningAccounts(
                      verified,
                      visibleReview.file,
                    );
                    if (
                      !matchesReviewSource(
                        opening,
                        visibleReview.file,
                        visibleReview.report,
                      )
                    )
                      throw new Error(
                        "The review does not match the source activity and accounts.",
                      );
                    setError(null);
                    setActivityBase(null);
                    setEndingBase({ file: visibleReview.file, opening });
                  } catch (failure) {
                    setError(
                      failure instanceof Error
                        ? failure.message
                        : "This review cannot use the guided ending form.",
                    );
                  }
                }}
              >
                Add ending statement
              </Button>
            )}
          {verified &&
            !endingBase &&
            !activityBase &&
            (visibleReview.report.status === "ENDING_RECONCILED" ||
              (visibleReview.report.status === "BLOCKED" &&
                visibleReview.report.ending_status === "MISMATCH" &&
                visibleReview.report.issues.every((issue) =>
                  ["ENDING_MISMATCH", "ENDING_ACCOUNT_MISSING"].includes(
                    issue.code,
                  ),
                ))) && (
              <Button
                variant="outline"
                onClick={() => {
                  try {
                    const restored = restoreEndingReview(
                      verified,
                      visibleReview.file.text,
                    );
                    if (
                      !matchesReviewSource(
                        restored.opening,
                        visibleReview.file,
                        visibleReview.report,
                      )
                    )
                      throw new Error(
                        "The review does not match the source activity and accounts.",
                      );
                    setError(null);
                    setEndingBase({
                      file: restored.file,
                      opening: restored.opening,
                      initialAccounts: restored.accounts,
                      cancelFile: visibleReview.file,
                    });
                  } catch (failure) {
                    setError(
                      failure instanceof Error
                        ? failure.message
                        : "This review cannot use the guided ending form.",
                    );
                  }
                }}
              >
                Edit supported ending statement
              </Button>
            )}
          <PortfolioLedgerResults
            key={visibleReview.report.input_sha256}
            report={visibleReview.report}
            file={visibleReview.file}
          />
        </>
      )}
      <PortfolioLedgerCandidates
        portfolioId={portfolioId}
        sourceReview={visibleReview}
      />
    </div>
  );
}
