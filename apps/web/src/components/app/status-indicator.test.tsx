import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ResponsiveDataTable } from "@/components/app/responsive-data-table";
import { StatusIndicator, statusTone } from "@/components/app/status-indicator";

describe("shared status and responsive data components", () => {
  it("maps availability and quality separately from positive or negative metrics", () => {
    expect(statusTone("FRESH")).toBe("positive");
    expect(statusTone("STALE")).toBe("warning");
    expect(statusTone("DATA_CHECK")).toBe("warning");
    expect(statusTone("UNAVAILABLE")).toBe("neutral");
    expect(statusTone("NOT_MIGRATED")).toBe("neutral");
    expect(statusTone("STALE_BASELINE")).toBe("warning");
    expect(statusTone("UNRESOLVED_REVIEW")).toBe("warning");
    expect(statusTone("ACKNOWLEDGED")).toBe("positive");
    expect(statusTone("DELIVERY_FAILED")).toBe("negative");
  });

  it("renders state in text as well as icon styling", () => {
    const html = renderToStaticMarkup(<StatusIndicator status="DATA_CHECK" />);
    expect(html).toContain("DATA CHECK");
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("text-warning");
  });

  it("provides semantic desktop table and mobile definition-list alternatives", () => {
    const html = renderToStaticMarkup(
      <ResponsiveDataTable
        caption="Availability"
        rows={[{ id: "quote", state: "STALE" }]}
        getRowKey={(row) => row.id}
        columns={[
          { id: "input", header: "Input", render: () => "Market quote" },
          { id: "state", header: "State", render: (row) => row.state },
        ]}
      />,
    );
    expect(html).toContain("<table");
    expect(html).toContain('<caption class="sr-only">Availability</caption>');
    expect(html).toContain("<dl");
    expect(html).toContain("Market quote");
  });
});
