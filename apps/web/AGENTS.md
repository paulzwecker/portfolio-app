# Web Agent Notes

Follow the root `AGENTS.md` and relevant domain documentation.

This file contains only frontend-specific guidance.

## Role

Next.js owns presentation and interaction.

The frontend must not independently calculate or redefine:

- valuation
- Expected IRR
- portfolio weights/gaps
- ranking logic
- scoring logic
- execution signals
- external-data reconciliation

Consume canonical API results.

## Product direction

The application should feel like professional investment-research software, not a spreadsheet reproduced in a browser.

Prioritize:

- information hierarchy
- compact but readable layouts
- progressive disclosure
- comparison
- historical context
- traceability
- responsive behavior

Avoid giant forms and unnecessary horizontal grids.

## Missing and historical data

Never render missing data as zero.

Make important states explicit:

- unavailable
- not migrated
- stale
- partial
- data check
- conflict

When presenting historical information, clearly distinguish:

- what was known at the time
- what was reported later
- current state

## Financial-model UX

Models should be understandable and editable through domain-oriented views.

Keep visually distinct:

- assumptions
- scenarios
- projections
- valuation
- outputs
- sources
- revision history

A user should be able to understand what changed between revisions and why.

Sheets-originated and web-originated revisions should appear as one coherent model history.

## Charts

Use charts when they improve analytical understanding.

Useful comparisons include:

- price vs historical Fair Value
- model forecast vs consensus vs actual
- estimate revisions
- model-output history
- portfolio current vs target

Do not add decorative charts simply because data exists.