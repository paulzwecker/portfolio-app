import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProviderQualityWarnings } from "./market-refresh-panel";

describe("provider quality warnings", () => {
  it("explains missing source rows without asserting expected-session coverage", () => {
    const html = renderToStaticMarkup(
      <ProviderQualityWarnings
        report={{
          domain_report: {
            normalization_warnings: [
              { code: "FX_ROWS_WITHOUT_CLOSE", message: "Skipped 1 row." },
            ],
          },
        }}
      />,
    );
    expect(html).toContain(
      "Some returned FX rows lacked a usable timestamp or positive close",
    );
    expect(html).toContain("do not establish expected-session coverage");
  });

  it("preserves unknown or absent evidence without displaying untrusted messages", () => {
    expect(renderToStaticMarkup(<ProviderQualityWarnings report={{}} />)).toBe(
      "",
    );
    const html = renderToStaticMarkup(
      <ProviderQualityWarnings
        report={{
          domain_report: {
            normalization_warnings: [
              { code: "UNKNOWN", message: "untrusted detail" },
            ],
          },
        }}
      />,
    );
    expect(html).toContain("normalization warning requires review");
    expect(html).not.toContain("untrusted detail");
  });
});
