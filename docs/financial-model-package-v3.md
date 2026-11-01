# Multi-Archetype Financial Model Package v3

## Purpose and scope

`financial-model-package-v3` supplies one versioned transport envelope for the
three native valuation archetypes already implemented by the API:

- 10-year UFCF DCF
- 10-year owner cash flow
- 10-year residual income with ROE fade

The `method` field is a strict discriminator. Each method has its own inputs,
unit contract, methodology version and projection output type. The package
does not translate one method's assumptions into another method, accept a
revision, persist a new model, or provide a second valuation engine. Native
calculations call the existing DCF and archetype engines.

No database migration is required: v3 is currently a validated package
serialization/replay contract, not a persisted database entity. Google Sheets
or an authorized package producer must still go through the existing model
preview and explicit-acceptance workflow before creating a canonical revision.

## Shared envelope

Every package contains:

- `identity`: source model key, canonical model/company/listing IDs when
  available, exact listing descriptors when supplied, model currency,
  valuation method, methodology version, and return-method code/version.
- `revision`: base canonical revision, external source revision, digest of the
  exact method input, effective time, author/time, source reference, rationale,
  and the mandatory `PROPOSAL_NOT_ACCEPTED` state.
- `source`: a discriminated source record with source contract hash and
  observation time. The DCF adapter embeds its complete v2 source package;
  additional models embed the existing portable v2 contract and may include
  an upstream source-identity hash.
- `method`: one of the three typed payloads below, including independently
  computed native outputs and method-specific projections.

All recorded timestamps must be timezone-aware. Decimal inputs and outputs
are serialized as canonical decimal strings. `parse_model_package_v3` reads
that representation while rejecting binary floating-point values;
`package_sha256` fingerprints the canonical serialized envelope. Repeated
builds from the same source contracts, inputs and observation time produce the
same hash. Validation checks the envelope hash, input digest, source digest,
identity/method links and deterministic native replay.

The package records the source's observation time, not a claim that Google
Sheets supplied a transactionally consistent snapshot. Source capture
consistency requirements remain those of the underlying v2 exporter and
portable contract.

## Method payloads

| Method                     | Input and unit contract                                                                                                                                              | Output treatment                                                                                                                                                                                                                                                                                                                                                     |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `UFCF_DCF_10Y_FADE`        | Existing `DcfCalculationInput-v1`; absolute operating values in model-currency billions, share count in billions, and per-listing-share values in model currency.    | Retains the source-published projections/valuation separately from projections recalculated by the native DCF engine. The P-GOOGL legacy reference price is undated and tagged `UNDATED_SOURCE_REFERENCE_FOR_PARITY_ONLY`; resulting return outputs are parity evidence, not a current market return. Enterprise return methodology remains explicit.                |
| `OWNER_CASH_FLOW_10Y`      | Existing `OwnerCashFlowInput-v1`; monetary amounts (including net cash) in model-currency billions, shares in billions, and valuation/projections per listing share. | Recalculates owner-cash-flow projections and fair values with the native engine. Since the portable source contract carries no eligible market quote, price-based upside, Expected IRR and excess remain unavailable, with an explicit partial state and reason. A legacy output snapshot, if attached, is labeled historical and is never used as candidate output. |
| `RESIDUAL_INCOME_10Y_FADE` | Existing `ResidualIncomeInput-v1`; book value and income per listing share, payout ratio as a fraction, and no separate share-count input.                           | Recalculates residual-income projections and fair values with the native engine. Price-based outputs remain explicitly unavailable until an eligible exact-listing quote is supplied through a future reviewed contract. An optional legacy output snapshot is historical only.                                                                                      |

Scenario names and exact probabilities are validated by the existing input
schemas; Bear/Base/Bull probabilities must sum exactly to one. The package
does not average scenario IRRs. The common normalized output field
`expected_cash_flow_irr` always carries a `return_methodology_code`: DCF
enterprise IRR must not be described as shareholder IRR or compared directly
with owner-cash-flow/residual-income equity IRR.

Currency is never silently converted. The current DCF parity adapter requires
the exact listing currency and model currency to match because its source
reference price is used only for source parity. Owner-cash-flow and
residual-income packages retain the canonical listing ID and its currency,
ticker and venue from a separate canonical identity response. The portable
candidate contains no eligible current market quote; price-dependent current
return outputs therefore stay unavailable.

## Reviewed source adapters

The DCF adapter wraps existing `financial-model-package-v2` packages from the
reviewed DCF templates (P-GOOGL, P-CPRT and P-AMZN). P-GOOGL is the tested
representative in this milestone and retains its existing source-output parity
validation. The v2 source package remains embedded and unchanged inside the v3
envelope.

The additional-model adapter consumes the existing
`AdditionalModelPortableContractV2`; it does not guess worksheet ranges or
parse undocumented legacy tabs. Its reviewed representative mapping is:

| Source model key | Native method              | Contract currency |
| ---------------- | -------------------------- | ----------------- |
| `W-TOST`         | `OWNER_CASH_FLOW_10Y`      | USD               |
| `W-HDFC`         | `RESIDUAL_INCOME_10Y_FADE` | INR               |

These adapters deliberately stop at those reviewed representatives. The
broader workbook inventory includes DCF models such as P-ASML, P-ISRG and P-MA,
owner-cash variants whose business economics are not the Toast model, and
residual-income W-SOFI. Their titles or family resemblance do not authorize
reuse of these source mappings. Existing native parity evidence covers
P-GOOGL/P-ASML/P-ISRG/P-MA and W-TOST; W-HDFC has residual-income parity
evidence but remains Drop/legacy-only. See the
[`model migration inventory`](model-migration-inventory.md) for per-family
limitations.

The adapter requires the existing canonical
`FinancialModelContractIdentity` response alongside the portable contract. It
checks source key, method, currency, canonical company/model/listing IDs and
listing descriptors, base revision, source revision, input digest, effective
time, authoring metadata, rationale and source reference. Unknown keys,
mismatched methods, currencies or canonical identities, missing typed inputs,
missing rationale/source reference, source-hash changes and stale/tampered
package replay fail closed. These representative contracts have fixture-backed
structural and numerical engine tests; this milestone did not perform live
workbook captures or assert fresh published outputs for W-TOST or W-HDFC.

Other model archetypes remain unsupported until their economics, input schema,
units, source mapping and native parity are reviewed. In particular, this
contract does not adapt dividend-discount, multiples, sum-of-parts, or other
methods into one of the supported three.

## Compatibility and migration

`build_package_from_dcf_v2` is the explicit DCF package-v2 to envelope-v3
adapter. `build_package_from_additional_contract` wraps the current portable
contract v2 for the reviewed owner-cash-flow and residual-income model keys;
its caller must supply the matching canonical `FinancialModelContractIdentity`
read from the application. They do not change either source package or its
stored history. The established financial-model-package-v1 P-GOOGL database
preview/acceptance path is left unchanged. V3 has no database importer yet; it
is not a replacement acceptance workflow and cannot create a canonical model
revision by itself. P-GOOGL's DCF source package supplies exact textual listing
identity but not canonical UUIDs; its existing separately guarded identity
resolver remains a required precondition before any later import.

## Verification

`apps/api/tests/test_financial_model_package_multi.py` covers the three
representative methods, v2-to-v3 wrapping, source and input hash checks,
canonical decimal-string serialization, deterministic replay/idempotence,
missing quote states, unsupported identities/methods/currencies, incomplete
source rationale, and preservation of the unaccepted state. The existing DCF
source-package parity suite remains a separate compatibility check.

No captured workbook/model packages or private financial values belong in Git.
