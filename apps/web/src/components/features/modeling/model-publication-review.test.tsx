import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ModelPublicationReview } from "./model-publication-review";
import {
  isModelPublicationParity,
  type ModelPublicationParity,
} from "@/lib/domain-contracts";

const evidence: ModelPublicationParity = {
  contract_sha256: "a".repeat(64),
  published_at: "2026-11-07T10:00:00Z",
  parity_status: "MATCH",
  absolute_tolerance: "0.0000001",
  comparisons: (["bear_fv", "base_fv", "bull_fv", "weighted_fv"] as const).map(
    (field) => ({
      field,
      published_value: "0",
      native_value: "0",
      difference: "0",
      matches: true,
    }),
  ),
};

function render(publication: ModelPublicationParity | null) {
  return renderToStaticMarkup(
    <ModelPublicationReview
      candidate={{
        publication,
        model_currency: "USD",
        previewed_at: "2026-11-07T10:01:00Z",
        preview_fingerprint: "b".repeat(64),
      }}
    />,
  );
}

describe("Published model review evidence", () => {
  it("retains exact financial decimal text, source hash and review identity", () => {
    const precise = "125.123456789012345678";
    const html = render({
      ...evidence,
      comparisons: evidence.comparisons.map((row) => ({
        ...row,
        published_value: precise,
        native_value: precise,
      })),
    });
    expect(html).toContain(precise);
    expect(html).toContain("USD per listing share");
    expect(html).toContain("Values match");
    expect(html).toContain("a".repeat(64));
    expect(html).toContain("b".repeat(64));
  });

  it("keeps explicit zero separate from unavailable native output", () => {
    expect(render(evidence)).toContain(">0</span>");
    const unavailable = {
      ...evidence,
      parity_status: "UNAVAILABLE" as const,
      comparisons: evidence.comparisons.map((row) => ({
        ...row,
        native_value: null,
        difference: null,
        matches: null,
      })),
    };
    expect(isModelPublicationParity(unavailable)).toBe(true);
    expect(render(unavailable)).toContain("Calculation unavailable");
    expect(render(unavailable)).toContain("Unavailable");
    expect(render(null)).toBe("");
  });

  it("validates typed source evidence and rejects malformed numeric values", () => {
    expect(isModelPublicationParity(evidence)).toBe(true);
    expect(
      isModelPublicationParity({
        ...evidence,
        comparisons: evidence.comparisons.map((row) => ({
          ...row,
          native_value: "-1",
          difference: "-1",
        })),
      }),
    ).toBe(true);
    expect(isModelPublicationParity({ ...evidence, comparisons: [] })).toBe(
      false,
    );
    expect(
      isModelPublicationParity({
        ...evidence,
        comparisons: [{ ...evidence.comparisons[0], published_value: 0 }],
      }),
    ).toBe(false);
    expect(
      isModelPublicationParity({ ...evidence, contract_sha256: "bad" }),
    ).toBe(false);
    expect(render({ ...evidence, parity_status: "MISMATCH" })).toContain(
      "Values differ",
    );
  });
});
