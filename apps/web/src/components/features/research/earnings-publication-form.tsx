"use client";

import { useState } from "react";
import type { components } from "@portfolio/contracts";
import { isEarningsBatch } from "@/lib/earnings-inbox";
import { Button } from "@/components/ui/button";

export function EarningsPublicationForm({
  portfolio,
  snapshot,
  refresh,
}: {
  portfolio: string;
  snapshot: string;
  refresh: () => void;
}) {
  const [file, setFile] = useState<File>();
  const [preview, setPreview] =
    useState<components["schemas"]["BatchResult"]>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function submit(action: "preview" | "publish") {
    if (!file || busy || (action === "publish" && !preview)) return;
    setBusy(true);
    setMessage("");
    try {
      if (file.size > 400000)
        throw new Error("Choose an assessment file under 400 KB.");
      const content: unknown = JSON.parse(await file.text());
      const res = await fetch(
        `/api/research/portfolios/${portfolio}/earnings-inbox/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            snapshot_id: snapshot,
            assessments: Array.isArray(content) ? content : [content],
            ...(action === "publish" ? { digest: preview?.digest } : {}),
          }),
        },
      );
      const result: unknown = await res.json();
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
      <summary>Publish earnings assessments</summary>
      <div className="mt-3 space-y-3">
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
        <Button disabled={!file || busy} onClick={() => void submit("preview")}>
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
