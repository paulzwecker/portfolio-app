# Canonical Portfolio Rank

Portfolio Rank is an immutable, run-based ordering for incremental-capital review
among companies with a positive current holding or positive strategic target. It
does not create or change holdings, target weights, lifecycle, model assumptions, or
Execution Pace. The accepted calculation is a direct implementation of the legacy
`Portfolio Score`, not an optimizer.

## Documented calculation

The workbook defines `Overview!S2` as a 100-point score:

```text
target-underweight credit (PORTFOLIO lifecycle only):
  min(max(target - current, 0) / max(target, 1%), 1) * 15
Expected IRR:
  max(min(Expected IRR, 25%), 0) / 25% * 30
10Y Durability:       score / 5 * 15
Compounder Quality:   score / 5 * 20
Execution:            score / 5 * 10
Risk:                 (6 - score) / 5 * 10
valuation uncertainty: -min((Bull FV - Bear FV) / Weighted FV, 2) / 2 * 10
negative Expected Excess:
  -max(min(-Expected Excess, 5%), 0) / 5% * 5
```

The score is ordered descending, then canonical listing ticker ascending. Values are
stored as exact decimals. Risk remains a distinct higher-is-worse input. No new
composite of estimate momentum, scenario probabilities, or Execution Pace is added.
The target-underweight term is only the workbook's documented 15-point contribution;
it is not an instruction to adjust the target.

## Input and comparison policy

A run takes a point-in-time snapshot of current holdings and accepted targets,
dated listing prices and FX, lifecycle, the latest accepted four-dimension score
assessments, and the selected normalized model output. The run requires a complete
holdings snapshot, an accepted target revision, a current weight that can be valued,
all four assessed scores, and the output fields required by the formula. A missing
target or score is not zero. Missing membership evidence is unavailable; incomplete
valuation or inconsistent definitions are `DATA_CHECK`.

The legacy normalized Expected IRR and native shareholder-cash-flow Expected IRR
are distinct methodologies. A run ranks the native cohort if at least one complete
native candidate exists; otherwise it can rank a comparable complete legacy cohort.
It never mixes the two. Complete legacy-only peers in a native run remain
`DATA_CHECK` until a comparable native model is available. This deliberately makes
coverage narrower than the source cached rank while preserving return semantics.

Runs and entry input snapshots are append-only. The score and its exact inputs,
component contributions, lifecycle, market weight, target weight, allocation gap,
price/FX evidence, model revision/output source, and methodology are stored with
each entry. Later market prices or model revisions do not rewrite an old run.

## Workbook reconciliation and live run

The source is `Portfolio_Watchlist.xlsx`, formula `Overview!S2`, cached score in
`Universe Registry!O`, and cached rank in `Universe Registry!L`. Workbook-only
formula fixtures cover 18 input-complete cases to `1e-8`; three cached cases have
missing required inputs. The 21 complete cached positions agree with descending
cached Portfolio Score and ticker tie order. `test_portfolio_rank.py` includes the
GOOGL source-score fixture (57.66995863) and score-bound, direction, floor/cap,
tie-order, and no-allocation-mutation coverage.

The first canonical application run ranks 3 of 21 current/target portfolio
companies. Eight are unavailable because a target or score input is missing. Ten
are `DATA_CHECK`: eight have legacy Expected IRR while native models participate in
the run, one model reference price predates a later exact-listing quote, and one
legacy contract is not a complete `PASS`. The current live result is recorded in
[`reconciliation/portfolio-rank-activation-2026-10-06.json`](reconciliation/portfolio-rank-activation-2026-10-06.json).

The workbook and canonical outputs remain separate. A workbook score is useful for
formula parity, but it does not override the canonical model's return definition or
populate a missing input.
