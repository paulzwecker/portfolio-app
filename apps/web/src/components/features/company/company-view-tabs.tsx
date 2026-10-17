"use client";

import { useRef } from "react";

export const companyViews = [
  { id: "overview", label: "Overview" },
  { id: "financials", label: "Financials" },
  { id: "valuation", label: "Valuation" },
  { id: "thesis", label: "Investment Thesis" },
  { id: "research", label: "Research & Evidence" },
  { id: "history", label: "Historical Analysis" },
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
      className="mb-6 flex min-w-0 gap-1 overflow-x-auto border-b pb-px"
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
          className={`shrink-0 border-b-2 px-3 py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            value === view.id
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {view.label}
        </button>
      ))}
    </div>
  );
}
