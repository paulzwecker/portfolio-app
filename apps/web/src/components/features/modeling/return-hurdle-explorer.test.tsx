import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { returnHurdleFixture } from "../../../../e2e/fixtures/return-hurdle";
import {
  ReturnHurdleExplorer,
  ReturnHurdleResult,
} from "./return-hurdle-explorer";

it("introduces a read-only workflow without fabricating a target or offering acceptance", () => {
  const data = returnHurdleFixture();
  const html = renderToStaticMarkup(
    <ReturnHurdleExplorer
      companyId={data.company_id}
      modelId={data.model_id}
      revisionId={data.revision_id}
      listingId={data.valuation_listing_id}
      currency={data.model_currency}
    />,
  );
  expect(html).toContain("Hypothetical · read-only");
  expect(html).toContain("Explore required return");
  expect(html).not.toContain('value="12"');
  expect(html).not.toContain("Accept revision");
  expect(html).not.toContain("$18.75");
});

it("explains enterprise semantics, fixed assumptions, source chronology and unavailable observed prices", () => {
  const html = renderToStaticMarkup(
    <ReturnHurdleResult data={returnHurdleFixture()} />,
  );
  expect(html).toContain("Enterprise return basis");
  expect(html).toContain("Not shareholder-distribution IRR");
  expect(html).toContain("$18.75");
  expect(html).toContain("Observed market comparison unavailable");
  expect(html).toContain("It does not change WACC");
  expect(html).toContain("not an average of scenario IRRs");
  expect(html).toContain("model ordinals");
  expect(html).toContain("Fictional browser fixture");
  expect(html).not.toContain("Observed market context");
});

it("preserves unavailable modeled return at a user-entered price", () => {
  const data = returnHurdleFixture();
  data.hypothetical_entry_price = "0.5";
  data.hypothetical_status = "UNAVAILABLE";
  data.hypothetical_unavailable_reason = "No conventional IRR exists.";
  const html = renderToStaticMarkup(<ReturnHurdleResult data={data} />);
  expect(html).toContain("Modeled return at your entry price");
  expect(html).toContain("Unavailable");
  expect(html).toContain("No conventional IRR exists.");
  expect(html).not.toContain(">0%<");
});
