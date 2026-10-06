# Execution Pace

Execution Pace is the portfolio timing decision downstream of the accepted
strategic target architecture. It answers how quickly to move toward that
target under current, comparable investment conditions. It is separate from
the company-level 1–5 **Execution** score, and it is not an order or automatic
allocation instruction.

The initial implementation is `legacy-execution-pace-v1`, based on the
`Portfolio` sheet's `Execution Pace` / `Pace Rationale` formulas in
`Portfolio_Watchlist.xlsx` (artifact SHA-256 in
[`workbook-map.md`](workbook-map.md)). It deliberately has a small explicit
domain function rather than a configurable rules engine.

## States

An available decision has one of these legacy-derived pace states:

| State          | Meaning                                                                                            |
| -------------- | -------------------------------------------------------------------------------------------------- |
| `ACCELERATE`   | Accelerate additions toward an underweight positive target.                                        |
| `BUILD`        | Add at a supported building pace under discount and correction/recovery context.                   |
| `NORMAL_BUILD` | Add at the normal pace where documented discount or near-fair branches support it.                 |
| `SMALL_LADDER` | Continue only with small staged additions while estimate revisions are negative.                   |
| `LADDER`       | Use staged additions when no documented faster/slower branch applies.                              |
| `HOLD`         | Allocation gap is inside the legacy 0.3 percentage-point band.                                     |
| `SLOW_LIMIT`   | Limit or slow additions due to rich valuation context, negative estimates, or price extension.     |
| `WAIT_LIMIT`   | Wait for a limit because return is below hurdle or price/estimate context is weak.                 |
| `PATIENT_TRIM` | Reduce an above-target positive position patiently under discount and correction/recovery context. |
| `TRIM_FASTER`  | Trim faster under a zero target plus rich/negative context, or rich valuation with extension.      |
| `NORMAL_TRIM`  | Reduce an above-target positive position at the normal pace.                                       |
| `PATIENT_EXIT` | Move patiently toward a zero target when discount and correction/recovery argue against haste.     |
| `NORMAL_EXIT`  | Move toward a zero target at the normal pace.                                                      |

Decision status is distinct from pace:

- `AVAILABLE` means a supported pace and rationale were calculated.
- `REVIEW` means one or more critical current inputs are missing, stale,
  incomparable, ambiguous, or outside the migrated semantics. `pace` remains
  null.
- `UNAVAILABLE` is reserved for an explicit unavailable decision state; it is
  not used as a neutral value.
- `NOT_APPLICABLE` means the company has neither a current holding nor an
  explicit target in the snapshot.
- A company without a recorded run has no state. The UI says so explicitly.

## Inputs and rule order

The API selects a point-in-time portfolio context and snapshots:

- accepted target revision, target weight, current holding snapshot, current
  weight, allocation gap and valued-allocation state;
- one unambiguous current model output/revision for the exact valuation listing,
  including Expected IRR, hurdle, currency, Weighted Fair Value, output status,
  and the source price used by that output;
- the latest known exact-listing split-adjusted price and its source, quality,
  currency and market/recorded timestamps;
- fresh price-regime facts and the source regime label;
- Estimate Momentum availability, direction, provider, freshness, quality and
  latest observation date;
- lifecycle as known at the run's `as_of` cutoff for traceability.

The rule first rejects incomplete critical data for review. It then checks
model reassessment/data-invalid flags and the legacy 0.3% absolute allocation
hold band. For an underweight company, below-hurdle Expected IRR and rich value
cap additions; negative revisions limit the pace; discount, at least 15%
Expected IRR or positive revisions combined with correction/recovery context
can support faster building. At/above target, the legacy zero-target exit and
positive-target trim branches apply. Weighted-upside zones use the workbook
thresholds: 25%, 10%, -10% and -25%. Price-regime labels are mapped only from
the documented source vocabulary; an unknown label requires review.

The application does not carry forward the workbook's hidden/fallback 9%
hurdle when a canonical hurdle is missing. It returns `REVIEW`, because a
missing required return is not an authored input. `DIRECTION_ONLY` is accepted
only when the canonical Estimate Momentum record has an observed usable
direction, fresh timestamp and `PASS` quality; it maps to the workbook's
explicit `COLLECTING` branch. When a legacy branch consumes estimate
direction, no history, insufficient history, a stale signal, or a quality
check remains `REVIEW`, never neutral momentum. Branches that do not consume
estimate direction (for example, a positive-target trim determined by target
gap, valuation and price regime) do not require an irrelevant estimate signal.

The current valuation zone is calculated using Weighted Fair Value against the
fresh exact-listing quote. The quote must share the model currency. The
Expected-IRR source price may not predate a later exact-listing quote. Price
regime and market quote must be fresh within five calendar days. Incomplete
portfolio market/FX valuation, multiple model/listing candidates, model output
quality issues, and unmapped regime labels all prevent an available pace.

## History and ownership

`execution_pace_runs` and `execution_pace_decisions` are append-only. Every
company decision stores its complete versioned input snapshot, source record
IDs, effective/observed dates, and rationale. API queries expose the latest
decision and history; historical runs are never recomputed from current state.

The calculation writes only these execution-decision records. It cannot alter
holdings, target revisions, lifecycle, model assumptions, scores, risk, quality,
or thesis. The UI keeps target and current weights visible alongside the pace,
but does not combine them into a new target or recommend an order quantity.

## Legacy comparison and limits

A read-only rehearsal against the current canonical database on 2026-10-06 found
219 tracked companies: 21 with a current Portfolio context, of which 2 could
receive an available pace (ASML Holding and Intuitive Surgical) and 19 require
review. The other 198 have no current holding or target and are
`NOT_APPLICABLE`. The main review blockers were 12 imported model outputs
without effective timestamps, 5 Portfolio lifecycle companies without an
explicit target, one Expected IRR with a non-current/non-comparable source
price, and one branch requiring unavailable Estimate Momentum history. This
rehearsal ran inside a transaction that was rolled back; it did not create
historical decisions. Exact counts are in the reconciliation JSON.

Representative cached formula results are pinned as deterministic regression
cases: DLO `Portfolio!K6` → `ACCELERATE`, SPGI `K11` → `SMALL / LADDER`, TSM
`K14` → `NORMAL BUILD`, MA `K15` → `WAIT / LIMIT`, and NVO `K21` →
`PATIENT EXIT`. These establish branch/threshold parity for the documented
examples; they do not certify all workbook rows or the current portfolio
population. See
[`reconciliation/execution-pace-legacy-2026-10-06.json`](reconciliation/execution-pace-legacy-2026-10-06.json).

The workbook's `Decision Signal History` contains a handful of previous
decisions, but its observation/recorded-time provenance is not sufficient to
import those rows as canonical historical runs. They remain reference evidence.
The first implementation also does not use business Execution score, thesis
state, or any undocumented qualitative judgment. Historical coverage starts
when a canonical run is recorded; it is not backfilled from current values.
