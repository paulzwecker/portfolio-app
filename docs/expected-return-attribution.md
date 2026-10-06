# Expected-return attribution

The attribution endpoint answers why the stored Expected IRR changed between
two selected history points. It is a derived comparison; it does not persist a
second version of source facts, recalculate accepted history in place, or change
model state.

## API and point selection

`GET /v1/companies/{company_id}/expected-return-attribution` requires
`prior_point_id` and `current_point_id`. The IDs come from
`GET /v1/companies/{company_id}/expected-return-history`. Optional `as_of` and
timezone-aware `known_at` cutoffs apply to both points. The endpoint rejects IDs
outside the selected company/cutoff and rejects a prior point later than the
current point.

Each endpoint in the response carries its history point ID, effective and
recorded timestamps, model and revision identity, methodology version, exact
valuation-price context and observation ID, and point-in-time consensus rows.
Consensus rows now include canonical observation IDs and source references, so
the underlying estimate records remain traceable. The estimate data is included
as context only: the supported native model engines do not consume consensus
estimates, so a coincident estimate revision is not presented as a cause of the
Expected IRR change.

## Native attribution method

For two points in the same native model series, with the same model type and
methodology version, the API rebuilds both retained input states and recalculates
16 combinations through that model's deterministic engine. Four factors switch
from prior to current values:

- exact model reference price;
- the Bear/Base/Bull probability vector;
- required-return inputs (DCF discount rates, owner-cash-flow required return,
  or residual-income cost of equity);
- other model assumptions, including operating/shareholder cash flows, balance
  sheet values and terminal growth.

The effect for each factor is its Shapley value: the average marginal effect
across every ordering in which the four factors could have changed. This makes
the effects symmetric when inputs interact and ensures the four effects add to
the recalculated endpoint difference. The native output at each endpoint must
first reconcile to its stored Expected IRR within `1e-12` IRR units. If endpoint
recalculation fails or an intermediate combination is invalid, no partial
effects are shown; the arithmetic endpoint change stays in residual.

Scenario fair-value and probability deltas, Weighted Fair Value, Hurdle and
Expected Excess are shown separately as context changes. Fair Value is not
treated as a proxy for Expected IRR contribution. Required-return effects can
change modeled terminal proceeds and therefore modeled IRR; the response labels
this as a model-rate assumption effect. A lower Hurdle remains a changed return
constraint and is never described as better operating economics. Hurdle itself
is displayed separately and is not added to the Expected IRR bridge.

The residual equals the stored endpoint Expected IRR difference less the four
attributed effects. It remains explicit and retains calculation/storage
reconciliation differences; it is never allocated to the largest driver.

## Incomplete and incompatible history

- Missing Expected IRR remains null and produces `MISSING_RETURN`; no zero or
  neutral return is substituted.
- Legacy output snapshots with a documented shared legacy field show their
  arithmetic endpoint change, but all of it remains residual as `OUTPUTS_ONLY`.
  The application does not reverse-engineer undocumented Expected Return Matrix
  behavior from cached values.
- A legacy/native semantic boundary produces `RETURN_SEMANTICS_CHANGE` and no
  numeric cross-method change.
- A model-series change or methodology-version change can show the arithmetic
  endpoint difference, but keeps the full difference residual. Methods are not
  cross-recalculated.
- Missing price or incomplete retained inputs leave the full native difference
  residual. No driver is inferred from weighted Fair Value or current market
  state.
- Consensus observation changes remain linked context until a supported model
  explicitly consumes them.

The endpoint currently reports calculated attribution on demand for native
UFCF DCF, owner-cash-flow and residual-income revisions. It does not create
forecast-quality scores, realized-return attribution, portfolio-level
attribution or investment decisions.

## Legacy comparison

The legacy workbook and imported output snapshots remain the source for
representative reported endpoint values. This milestone does not claim numeric
parity for a workbook change decomposition: the available normalized snapshots
do not establish a documented rule for separating price, probability, hurdle
and model effects. The native bridge is reconciled against the application's
stored deterministic endpoint calculations instead. Any later legacy parity
work must first identify an authoritative, documented counterfactual method.
