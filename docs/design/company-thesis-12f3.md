# Milestone 12F.3 — Company Investment Thesis UX

## User question and information hierarchy

The Investment Thesis view answers: **why may this business compound over the
long term, and what could invalidate that view?** The view now follows the
Company Explorer Glance → Analysis → Evidence hierarchy:

1. **Investment case at a glance** — the accepted thesis statement, rationale,
   confidence, observation/recorded times, source identity, and compact previews
   of advantage/durability, growth/reinvestment, risks/breakers and open
   questions.
2. **Claims & evidence** — a selectable claim list grouped by the canonical claim
   types. Selecting a claim reveals its status, confidence, uncertainty and all
   supporting, contradicting and contextual evidence.
3. **Revision history** — prior immutable snapshots remain expandable. The view
   compares stable claim keys and labels added, changed, removed and unchanged
   claims; it does not rebuild history from current state.
4. **Research next** — open canonical research-queue conditions for the company,
   with the queue reason, responsible workflow and an explicit link back to the
   queue. Completion remains an analyst action and never accepts a thesis.
5. **Investment quality** — the existing score section remains a separate panel
   after the thesis case. 10Y Durability and Compounder Quality remain distinct,
   as do Execution and Risk; no composite is introduced.

## Implementation

`CompanyInvestmentThesis` is the focused domain component mounted by the
`thesis` Company Explorer tab. It reuses `PageSection`, `Card`, `StatusIndicator`,
`SourceReference`, `EmptyState`, `DetailDrawer` and the canonical `useResearch`
data access path. The component consumes the existing thesis and research-queue
contracts and performs only presentation-level grouping and revision comparison.
No score, thesis, evidence, lifecycle, model or ranking calculation was added to
React.

Evidence inspection uses the shared detail drawer. It preserves source document
and reported-fundamental identifiers, publication dates, excerpts, notes and
external links. The inline claim view keeps contradicting evidence visible as an
explicit relationship; it is never treated as a neutral or resolved signal.

The summary links to `/company/{id}?view=financials` and
`/company/{id}?view=valuation`, retaining canonical company context. Research
links use the existing queue search contract and do not mutate queue state.

## Missing and historical states

An empty stream is rendered as **No accepted thesis revision**, with an explicit
explanation that missing is not a neutral assessment. Withdrawn revisions remain
auditable and show their recorded time. Missing claims, missing evidence, missing
source dates and unavailable queue data have dedicated text states. Accepted
revisions and prior snapshots are not edited or synthesized in the browser.

## Visual and responsive review

The live local Company Explorer was reviewed at desktop width using a real
Alphabet record with no accepted thesis. The missing-state card, research-next
section, exact listing context, tab rail and independent quality assessments were
readable without horizontal overflow. The existing desktop/mobile Playwright
Company Explorer workflow was extended to exercise a populated thesis fixture:
claim selection, contradicting reported-fact evidence, source inspection drawer,
revision history and mobile navigation all passed.

The populated layout uses a single-column stack on narrow screens and a
claim-list/detail split from the `lg` breakpoint upward. Evidence cards wrap
source metadata and actions, while the drawer remains full-width on mobile. All
claim selectors are keyboard-focusable buttons with `aria-pressed`; the evidence
drawer has a labeled close action and Escape handling from the shared component.

## Deliberate limits

- The application does not author or accept thesis revisions in this view;
  publication and review safeguards remain in the external research workflow.
- The canonical contract does not encode explicit claim-to-claim relationships,
  so catalysts and thesis breakers are presented as separate claim groups rather
  than inferred links.
- Queue freshness is represented by the queue's own open/complete state and
  source timestamps; the frontend does not invent an age threshold.
- Real local development data currently has sparse thesis coverage, so the live
  view legitimately shows the missing state. Populated and conflicting states
  are covered by contract fixtures and browser tests.
