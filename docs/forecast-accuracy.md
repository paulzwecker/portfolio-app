# Forecast accuracy and consensus benchmarking

Forecast accuracy is a read-only comparison of genuinely recorded forecasts with
later reported financial facts. It is an operational measure of forecast error,
not investment return, valuation, or a researcher/model ranking. It does not
calibrate scenario probabilities.

## Sources and ownership

The comparison reads three canonical sources without copying them into a second
forecast store:

- **Agent research** reads published `ResearchForecast` records and their immutable
  `ResearchRevision` provenance. Author, stream, contract version, fiscal period,
  source observation time, application recorded time and supersession are retained.
- **Financial models** read accepted native model revision projections and the
  revision's methodology, scenario, probability, author/actor and provenance.
  Bear/Base/Bull projections are displayed as conditional scenarios and are not
  scored as point forecasts. Current model revisions store ordinal projection years
  without a fiscal-year anchor, so they cannot yet be joined to reported periods.
  UFCF, owner cash flow and net-income-per-share are also kept distinct from exact
  reported metrics; no method bridge is invented here.
- **Analyst consensus** reads provider-specific estimate observations with the
  provider mapping effective and recorded at that observation's knowledge time.
  Only the selected continuity provider is eligible for a comparison. Alternate
  providers remain visible with an explicit status and are never blended.

Reported results come from the canonical reported-fundamental resolver at an
independent outcome cutoff. Its source precedence, conflict, quality and
restatement selection remain authoritative. A later restatement changes the result
only at a later outcome cutoff; the earlier cutoff continues to reproduce the
earlier-known result.

## Point-in-time and alignment rules

The forecast knowledge time is the later of source observation/publication time and
application recorded time. For accepted model revisions, effective time is retained
separately from source observation time, and forecast knowledge time is the later of
revision effective time and application recorded time. A source without a
trustworthy observation or effective time is retained but cannot establish forecast
horizon. A canonical actual is eligible only when its publication time is known and
it was published after the forecast knowledge
time. If an actual was already available through a canonical observation, its source
publication time is missing, or a date-only filing shares the forecast date, the
comparison stays explicitly unavailable. Effective, observed and recorded times are
also bounded by the outcome cutoff. No later reported fact can be shown as forecast-
time knowledge.

Research and consensus forecasts match reported periods by exact period end when
available, while also checking stated fiscal year and period when present. If the
forecast has no period end, it must have an explicit fiscal year and period. A
provider label such as `FY+1` is retained as source context and is not translated
into a fiscal year. Annual and quarterly periods remain separate. The model's
ordinal `forecast_year` is never inferred from its revision timestamp.

Values are compared only when the canonical metric, period, currency and unit match.
No implicit FX conversion is applied. In particular, the system does not silently
equate reported operating income with EBIT, net income per share with diluted EPS,
or operating cash flow less capex with a model-specific free-cash-flow definition.
Those rows remain visible with an unavailable reason until a documented exact metric
or deterministic bridge is available.

## Error and aggregation

Signed error is `forecast - actual`; a positive value means the forecast was above
the realized fact. Absolute error is its absolute value. Signed relative error is
`(forecast - actual) / abs(actual)` and absolute relative error is its absolute
value. Relative error is undefined when the actual is zero; absolute error remains
available. The response retains original values, currencies, units, timestamps,
actual source observation, quality and supersession links.

The API can return multiple observations for a fiscal period, preserving the forecast
revision timeline and the horizon at which each was made. Summary MAPE and mean
signed percentage error are grouped by source identity, methodology/version, metric,
fiscal-period type and horizon bucket. Repeated revisions of one period count once
within a summary bucket. At least five distinct fiscal periods with valid comparisons
are required. Smaller samples report `INSUFFICIENT_SAMPLE`; they are not used to rank
people or models.

## API and Explorer

`GET /v1/companies/{company_id}/forecast-accuracy` accepts optional `metric`,
`source`, `period_type`, `fiscal_year`, `fiscal_period`, timezone-aware
`outcome_known_at`, and `limit` (1–500). The default outcome cutoff is current UTC
time. The Company Explorer offers source, metric, annual/quarterly and outcome-date
filters. It shows forecast and actual values, source/methodology, horizon,
publication/observation/recorded times, errors, restatement links and explicit
unavailable states. The date control uses the end of the selected UTC day; callers
of the API can provide a more precise timestamp.

## Current local coverage

The canonical PostgreSQL state inspected on 2026-10-15 contains 219 companies, zero
published agent research forecasts, 67 consensus observations, zero consensus
observations with an observation timestamp, zero with an absolute period end, zero
reported-fundamental observations and 15 native model revisions. Thus there are
currently no real forecast-versus-actual comparisons. Consensus records are retained
as unscored because neither their source time nor absolute fiscal period can establish
a genuine historical forecast. The native revisions appear with scenario and
methodology context, but no fiscal-year mapping or accuracy score is invented.

At present the exact reported metric path is implemented for Revenue, which is the
only directly represented metric supported by the current facts query. EPS, EBIT,
EBITDA and free-cash-flow forecasts can be inspected but remain unavailable for
scoring until exact canonical reported metrics and safe unit/period mappings exist.
Operating income and cash-flow statement facts are not substituted for those
definitions. No historical forecasts or actuals were fabricated by this feature.

Future evaluation becomes meaningful after actual source coverage,
provider-consistent consensus history, agent forecast history, and explicit model
fiscal-period anchors are present. Scenario distribution and decision-signal
evaluation is described in [decision-evaluation.md](decision-evaluation.md); it
retains the same exact-period and point-in-time rules used here.
