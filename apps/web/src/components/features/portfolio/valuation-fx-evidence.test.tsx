import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ValuationFxEvidence } from "./valuation-fx-evidence";

function render(
  values: Partial<Parameters<typeof ValuationFxEvidence>[0]> = {},
) {
  return renderToStaticMarkup(
    <ValuationFxEvidence
      sourceCurrency="USD"
      targetCurrency="EUR"
      rate="0.923456789012"
      effectiveAt="2026-11-09T16:00:00Z"
      {...values}
    />,
  );
}

describe("Portfolio FX evidence", () => {
  it("shows the API rate at full precision with its effective time", () => {
    const html = render({ syncStatus: "NON_SYNCHRONOUS" });
    expect(html).toContain("1 USD = 0.923456789012 EUR");
    expect(html).toContain("FX effective");
    expect(html).toContain("FX effective and quote observation times differ");
    expect(html).not.toContain("non-synchronous close");
  });
  it("states when no conversion is needed", () => {
    expect(
      render({ sourceCurrency: "EUR", rate: null, effectiveAt: null }),
    ).toContain("No currency conversion required");
  });
  it("does not invent an FX rate or time", () => {
    expect(render({ rate: null, effectiveAt: null })).toContain(
      "FX rate not recorded for this valuation (USD → EUR)",
    );
    expect(render({ rate: null })).not.toContain("1 USD =");
    expect(render({ effectiveAt: null })).toContain(
      "FX effective time unavailable",
    );
    expect(render({ sourceCurrency: null })).toContain(
      "Source currency unavailable",
    );
  });
});
