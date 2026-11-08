import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  DcfSensitivityGrid,
  DcfSensitivityPanel,
  sensitivityShiftLabel,
} from "./dcf-sensitivity";
import { isDcfSensitivity, type DcfSensitivity } from "@/lib/domain-contracts";

function fixture(): DcfSensitivity {
  return {
    calculation_version: "ufcf-dcf-sensitivity-v1",
    model_id: "11111111-1111-4111-8111-111111111111",
    revision_id: "22222222-2222-4222-8222-222222222222",
    revision_number: 3,
    methodology_version: "ufcf-dcf-fade-v1",
    model_currency: "USD",
    discount_rate_shifts: ["-0.01", "0", "0.01"],
    terminal_growth_shifts: ["-0.005", "0", "0.005"],
    scenarios: ["BEAR", "BASE", "BULL"].map((scenario) => ({
      scenario: scenario as "BEAR" | "BASE" | "BULL",
      probability: scenario === "BASE" ? "0.6" : "0.2",
      year5_discount_rate: "0.09",
      terminal_growth: "-0.01",
    })),
    cells: ["-0.01", "0", "0.01"].flatMap((discount_rate_shift) =>
      ["-0.005", "0", "0.005"].map((terminal_growth_shift) => ({
        discount_rate_shift,
        terminal_growth_shift,
        status: "AVAILABLE",
        unavailable_reason: null,
        bear_fv: "-2",
        base_fv: "0",
        bull_fv: "40",
        weighted_fv: "20.123456789012345678",
      })),
    ),
  };
}

describe("DCF sensitivity presentation and contract", () => {
  it("shows per-share currency, exact revision, axes, scenarios and hypothetical boundaries", () => {
    const data = fixture();
    expect(isDcfSensitivity(data)).toBe(true);
    const html = renderToStaticMarkup(<DcfSensitivityGrid data={data} />);
    expect(html).toContain("Fair value per share · USD");
    expect(html).toContain("Accepted revision 3");
    expect(html).toContain("Accepted assumptions");
    expect(html).toContain("Discount rate shift");
    expect(html).toContain("Terminal growth -1%");
    expect(html).toContain("Investor hurdle and shareholder returns");
    expect(html.match(/\$20\.12/g)).toHaveLength(9);
    expect(sensitivityShiftLabel("0.005")).toBe("+0.5 pp");
    expect(sensitivityShiftLabel("-0.01")).toBe("-1 pp");
    expect(sensitivityShiftLabel("0")).toBe("0 pp");
  });

  it("preserves unavailable cells and explains their reason visibly", () => {
    const data = fixture();
    data.cells[0] = {
      ...data.cells[0],
      status: "INVALID_ASSUMPTIONS",
      unavailable_reason: "Terminal growth reaches the discount rate.",
      weighted_fv: null,
      bear_fv: null,
      base_fv: null,
      bull_fv: null,
    };
    expect(isDcfSensitivity(data)).toBe(true);
    const html = renderToStaticMarkup(<DcfSensitivityGrid data={data} />);
    expect(html).toContain("Unavailable rate combinations");
    expect(html).toContain("Terminal growth reaches the discount rate.");
    expect(html).not.toContain("$0.00");
  });

  it("rejects omitted, duplicate, numeric, mismatched and unavailable-valued grid data", () => {
    const missing = fixture();
    missing.cells.pop();
    expect(isDcfSensitivity(missing)).toBe(false);
    const duplicate = fixture();
    duplicate.cells[8] = duplicate.cells[0];
    expect(isDcfSensitivity(duplicate)).toBe(false);
    const invalidCoordinate = fixture();
    invalidCoordinate.cells[0].discount_rate_shift = "-0.02";
    expect(isDcfSensitivity(invalidCoordinate)).toBe(false);
    const invalidOutput = fixture();
    invalidOutput.cells[0].weighted_fv = null;
    expect(isDcfSensitivity(invalidOutput)).toBe(false);
    expect(
      isDcfSensitivity({
        ...fixture(),
        discount_rate_shifts: [-0.01, 0, 0.01],
      }),
    ).toBe(false);
    expect(isDcfSensitivity({ ...fixture(), model_id: "unverified" })).toBe(
      false,
    );
    const scenarios = fixture();
    scenarios.scenarios[2] = scenarios.scenarios[0];
    expect(isDcfSensitivity(scenarios)).toBe(false);
  });

  it("starts collapsed without requesting or exposing acceptance actions", () => {
    const html = renderToStaticMarkup(
      <DcfSensitivityPanel
        modelId={fixture().model_id}
        revisionId={fixture().revision_id}
      />,
    );
    expect(html).toContain("Explore sensitivity");
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("Hypothetical · read-only");
    expect(html).not.toContain("<table");
    expect(html).not.toContain("Accept revision");
  });
});
