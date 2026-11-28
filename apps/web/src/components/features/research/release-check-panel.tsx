"use client";

import { useState } from "react";
import { useResearch } from "@/hooks/use-research";
import { Button } from "@/components/ui/button";
import { type EarningsInbox, isReleaseDrafts } from "@/lib/earnings-inbox";
import { EarningsPublicationForm } from "./earnings-publication-form";

export function ReleaseCheckPanel({
  portfolio,
  snapshot,
  rows,
  refresh,
}: {
  portfolio: string;
  snapshot: string;
  rows: EarningsInbox["rows"];
  refresh: () => void;
}) {
  const endpoint = `portfolios/${portfolio}/earnings-inbox`;
  const drafts = useResearch(endpoint + "/drafts", isReleaseDrafts);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string[]>([]);
  const scope = new Map(
    rows
      .filter((row) => row.release_check_available)
      .map((row) => [row.listing_id, row.listing]),
  );
  async function check() {
    setBusy(true);
    setStatus([]);
    try {
      for (const [id, name] of scope) {
        try {
          const res = await fetch(`/api/research/${endpoint}/check/${id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
          if (!res.ok) throw new Error();
          const result = await res.json();
          setStatus((old) => [...old, `${name}: ${result.message}`]);
        } catch {
          setStatus((old) => [
            ...old,
            `${name}: check failed. Verify the SEC or agent configuration and retry.`,
          ]);
        }
      }
    } finally {
      setBusy(false);
      drafts.retry();
    }
  }
  return (
    <section className="space-y-2" aria-label="Issuer release drafts">
      <Button disabled={busy || !scope.size} onClick={() => void check()}>
        {busy ? "Checking issuers…" : "Check for new releases"}
      </Button>
      <div aria-live="polite">
        {status.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
      {drafts.error && (
        <p role="alert">
          Release drafts could not be loaded.{" "}
          <button onClick={drafts.retry}>Retry</button>
        </p>
      )}
      {Array.isArray(drafts.data) &&
        drafts.data.map((draft) => (
          <EarningsPublicationForm
            key={draft.id}
            portfolio={portfolio}
            snapshot={snapshot}
            draft={draft}
            refresh={() => {
              drafts.retry();
              refresh();
            }}
          />
        ))}
    </section>
  );
}
