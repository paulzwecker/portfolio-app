"use client";

import { useState } from "react";
import type { components } from "@portfolio/contracts";
import { isEarningsBatch } from "@/lib/earnings-inbox";
import { Button } from "@/components/ui/button";

export function EarningsPublicationForm({
  portfolio,
  snapshot,
  refresh,
  draft,
}: {
  portfolio: string;
  snapshot: string;
  refresh: () => void;
  draft?: components["schemas"]["Draft"];
}) {
  const [file, setFile] = useState<File>();
  const [preview, setPreview] =
    useState<components["schemas"]["BatchResult"]>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function submit(action: "preview" | "publish") {
    if ((!file && !draft) || busy || (action === "publish" && !preview)) return;
    setBusy(true);
    setMessage("");
    try {
      if (file && file.size > 400000)
        throw new Error("Choose an assessment file under 400 KB.");
      const content: unknown = draft
        ? draft.assessment
        : JSON.parse(await file!.text());
      const res = await fetch(
        `/api/research/portfolios/${portfolio}/earnings-inbox/${draft && action === "publish" ? `drafts/${draft.id}/publish` : action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            snapshot_id: snapshot,
            ...(action === "publish" && draft
              ? {}
              : { assessments: Array.isArray(content) ? content : [content] }),
            ...(action === "publish" ? { digest: preview?.digest } : {}),
          }),
        },
      );
      const result: unknown = await res.json();
      if (
        res.ok &&
        draft &&
        action === "publish" &&
        typeof result === "string"
      ) {
        setPreview(undefined);
        refresh();
        return;
      }
      if (!res.ok || !isEarningsBatch(result))
        throw new Error(
          res.status === 409
            ? "The holdings or model changed. Refresh and preview again."
            : "Check the assessment file, model revision and reviewer access, then retry.",
        );
      if (action === "preview") setPreview(result);
      else {
        setMessage(
          `${result.revision_ids.length} assessments confirmed in the inbox.`,
        );
        setPreview(undefined);
        refresh();
      }
    } catch (error) {
      setPreview(undefined);
      setMessage(
        error instanceof SyntaxError
          ? "Choose a valid JSON assessment file."
          : error instanceof Error
            ? error.message
            : "Publication failed. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="rounded-md border p-3">
      <summary>
        {draft
          ? `${draft.listing} · Release draft · revision ${draft.revision}`
          : "Publish earnings assessments"}
      </summary>
      <div className="mt-3 space-y-3">
        {draft ? (
          <p>
            {draft.accession} ·{" "}
            <a
              className="underline"
              href={draft.source_url}
              target="_blank"
              rel="noreferrer"
            >
              SEC earnings exhibit
            </a>
          </p>
        ) : (
          <label className="block">
            Assessment file (JSON)
            <input
              type="file"
              accept=".json,application/json"
              disabled={busy}
              className="block"
              onChange={(e) => {
                setFile(e.target.files?.[0]);
                setPreview(undefined);
                setMessage("");
              }}
            />
          </label>
        )}
        <Button
          disabled={(!file && !draft) || busy}
          onClick={() => void submit("preview")}
        >
          Preview
        </Button>
        {preview && (
          <>
            <ul className="space-y-3">
              {preview.items.map((item, index) => (
                <li key={index}>
                  <strong>
                    {item.listing} · Revision {item.revision} ·{" "}
                    {item.conclusion.replaceAll("_", " ")}
                  </strong>
                  <p>
                    {item.driver.replaceAll("_", " ")} · {item.accepted_value} ·{" "}
                    {item.comparable_period}
                  </p>
                  <blockquote>{item.passage}</blockquote>
                  <p>{item.rationale}</p>
                  <a
                    href={item.source}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    Issuer publication
                  </a>
                </li>
              ))}
            </ul>
            {draft?.replacement != null && (
              <p>
                Proposed base Year 1 input:{" "}
                {(Number(draft.replacement) * 100).toFixed(2)}%. Publishing
                opens a separate model proposal for review.
              </p>
            )}
            <Button disabled={busy} onClick={() => void submit("publish")}>
              Publish {preview.items.length}{" "}
              {preview.items.length === 1 ? "assessment" : "assessments"}
            </Button>
          </>
        )}
        {message && <p role="status">{message}</p>}
      </div>
    </details>
  );
}
