"use client";

import { useRef } from "react";

export const companyViews = [
  { id: "overview", label: "Overview" },
  { id: "financials", label: "Financials" },
  { id: "history", label: "Prices & history" },
  { id: "valuation", label: "Valuation" },
  { id: "thesis", label: "Thesis & risks" },
  { id: "research", label: "Evidence" },
] as const;

export type CompanyView = (typeof companyViews)[number]["id"];

const legacyAnchorViews: Record<string, CompanyView> = {
  overview: "overview",
  attention: "overview",
  "investment-quality": "thesis",
  "market-facts": "history",
  "reported-fundamentals": "financials",
  "source-documents": "research",
  "consensus-estimates": "financials",
  "estimate-momentum": "history",
  "temporal-alignment": "history",
  "canonical-models": "valuation",
  "canonical-model-archetypes": "valuation",
  "model-migration-status": "valuation",
  "model-output-history": "valuation",
  "expected-return-history": "history",
  "ranking-context": "history",
  "execution-pace": "history",
  "investment-thesis": "thesis",
  "research-forecasts": "financials",
  "risk-assessments": "research",
};

export function companyViewFromLocation(
  search: string,
  hash: string,
): CompanyView {
  const requested = new URLSearchParams(search).get("view");
  if (companyViews.some((view) => view.id === requested))
    return requested as CompanyView;
  return legacyAnchorViews[hash.replace(/^#/, "")] ?? "overview";
}

export function CompanyViewTabs({
  value,
  onChange,
}: {
  value: CompanyView;
  onChange: (value: CompanyView) => void;
}) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function moveFocus(currentIndex: number, key: string) {
    let nextIndex = currentIndex;
    if (key === "ArrowRight")
      nextIndex = (currentIndex + 1) % companyViews.length;
    if (key === "ArrowLeft")
      nextIndex =
        (currentIndex - 1 + companyViews.length) % companyViews.length;
    if (key === "Home") nextIndex = 0;
    if (key === "End") nextIndex = companyViews.length - 1;
    if (nextIndex === currentIndex) return;
    tabRefs.current[nextIndex]?.focus();
    onChange(companyViews[nextIndex].id);
  }

  return (
    <div
      role="tablist"
      aria-label="Company research views"
      className="my-5 grid min-w-0 grid-cols-3 gap-1 rounded-lg border bg-card p-1 lg:flex"
    >
      {companyViews.map((view, index) => (
        <button
          key={view.id}
          ref={(node) => {
            tabRefs.current[index] = node;
          }}
          id={`company-tab-${view.id}`}
          type="button"
          role="tab"
          aria-selected={value === view.id}
          aria-controls="company-view-panel"
          tabIndex={value === view.id ? 0 : -1}
          onClick={() => onChange(view.id)}
          onKeyDown={(event) => {
            if (
              ["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)
            ) {
              event.preventDefault();
              moveFocus(index, event.key);
            }
          }}
          className={`min-w-0 rounded-md border-b-2 px-2 py-3 text-xs sm:px-3 sm:text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            value === view.id
              ? "border-primary bg-primary/5 text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {view.label}
        </button>
      ))}
    </div>
  );
}
