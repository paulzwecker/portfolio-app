# Research Experience — Milestone 11G

The Research workspace unifies candidate progression, derived research work, external proposal review and the evidence change feed. It reuses the application’s existing APIs and revision semantics; it does not add another research workflow or approval store.

## Route and page ownership

| Current route             | Purpose                                                            | Research workspace view                     |
| ------------------------- | ------------------------------------------------------------------ | ------------------------------------------- |
| `/universe`               | Compare tracked companies across lifecycle states                  | Discovery and comparison remain in Universe |
| `/research`               | Research home                                                      | Review Queue by default                     |
| `/research?view=pipeline` | Candidate gate progression                                         | Candidate Pipeline                          |
| `/research?view=queue`    | Open and completed research work, evidence triggers, agent handoff | Review Queue                                |
| `/research?view=reviews`  | Model, research/thesis and risk submissions                        | Agent proposals                             |
| `/research?view=changes`  | Canonical material-change feed                                     | Change feed                                 |
| `/candidates`             | Preserved deep link                                                | Redirects to Candidate Pipeline             |
| `/research-queue`         | Preserved deep link                                                | Redirects to Review Queue                   |
| `/attention`              | Preserved change-feed link                                         | Redirects to Change feed                    |
| `/model-sync`             | Preserved external-model review link                               | Redirects to Agent proposals                |

The application shell exposes Universe and Research under one Research navigation group. Company and evidence links retain canonical IDs and open Company Explorer directly.

## Information hierarchy

The workspace follows the shared Glance → Analysis → Evidence/Audit pattern:

1. Four workload counts show candidate companies, open review tasks, unaccepted agent proposals and open evidence triggers. An unavailable feed is labeled unavailable, never as an empty queue.
2. The selected research view presents the relevant task list, filters, candidate gates or proposal comparison.
3. Source records, timestamps, preview diffs and immutable revision history stay expandable or in the detail pane.

Universe remains the company-comparison surface. Its lifecycle, rank, score, price/model coverage, research state and comparable-return sorting all use canonical API values. Expected IRR sorting requires an explicit canonical comparability cohort; it does not sort across incompatible methods.

## Shared workflow conventions

- **Candidate Pipeline:** A submission records a complete gate snapshot against the current candidate revision. The result is shown outside the form so a refresh cannot erase confirmation. A recommendation is research state and does not change lifecycle, holdings or target weights.
- **Research Queue:** Open conditions can be grouped by Candidate, thesis/evidence, model, or risk/readiness work and filtered by lifecycle/company. Completion appends a queue completion record and remains independent from proposal acceptance and investment state.
- **Agent handoff:** The queue view retains manual publication of bounded work to the application-owned Sheets feed and manual publication of canonical portfolio context. These are outbound deliveries, not approval events. Partial valuation and freshness metadata remain part of the existing publication contract.
- **Proposal review:** Model, research/thesis and risk inbox candidates share one search/list/detail pattern. The detail shows contract version, external revision, canonical base, author, rationale, source, observation/recording times, validation state and domain diff. Domain-specific preview and acceptance endpoints remain authoritative. Research and thesis previews return the base identity and proposed content, but not the prior revision payload; the UI says so explicitly and does not imply a field-level diff.
- **Approval safeguard:** A reviewer and rationale are required. Accept and reject each require an explicit second confirmation. Acceptance is unavailable for unresolved model/research conflicts or invalid contracts. A risk assessment with a stale portfolio baseline requires a separate acknowledgment. Acknowledging agent delivery or completing a research task is not approval.
- **Audit:** Accepted and rejected proposals appear in review history with canonical responses. Queue completion history and Candidate revision history remain separately visible because they answer different questions.
- **Change feed:** Material attention events are shown separately from due work and proposed edits; a source event is not presented as an interpretation or an instruction to change a model.

## Component ownership

`components/features/company/universe-page.tsx` owns the Universe comparison view; its App Router page is a thin route adapter. Research components under `components/features/research/` own the pipeline, queue, Sheets work handoff, proposal review and workspace composition. Generic page headers, cards, badges, links, status indicators and financial formatting remain in shared application/UI components. `AttentionCenter` is reused for the change-feed view rather than copied into a second implementation.

Unreferenced files that duplicated a Portfolio allocation page under `features/research/` were removed after confirming there were no imports. Candidate, queue and proposal behavior now lives in dedicated feature components.

## Verification and acceptance criteria

- Portfolio, Watchlist and Candidate work can be searched and filtered without changing lifecycle.
- Universe return comparisons stay inside explicit methodology cohorts; missing returns remain unavailable.
- Duplicate trigger conditions stay deduplicated by the backend; queue completion does not delete trigger or proposal history.
- A stale proposal remains visibly blocked or acknowledgment-gated; a browser test confirms no accept request is sent until the reviewer presses the final confirmation.
- Missing inbox data, evidence, timestamps and provider context remain explicit.
- Candidate, queue and proposal flows are operable by keyboard, retain visible focus, and fit mobile viewports without page-level horizontal overflow.

## Boundaries and remaining work

Research Queue conditions are derived by the backend and can change when source state changes. Proposal lists and diffs are domain-specific API contracts; the UI shows the complete preview record if a domain introduces a new diff shape. Research and thesis review should be cross-checked against Company Explorer history when a field-by-field prior-state comparison is needed, because the existing preview contract does not return the prior payload. This milestone does not add proposal-comment threads, bulk approval, a generic task system, new ranking logic, lifecycle transitions, or model/research interpretation. Direct authenticated API publication paths remain governed by their existing contracts; Sheets stays a transport and authoring environment rather than a canonical store.
