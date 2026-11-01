"""Versioned multi-archetype model packages over existing model contracts.

This module is a transport and deterministic replay boundary. It does not
accept or persist model revisions and it does not contain an alternate engine.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Annotated, Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portfolio_api.domain import schemas
from portfolio_api.domain.models import DcfScenario
from portfolio_api.financial_model_archetypes import (
    ArchetypeCalculation,
    OwnerCashFlowProjectionCalculation,
    ResidualIncomeProjectionCalculation,
    calculate_owner_cash_flow,
    calculate_residual_income,
)
from portfolio_api.financial_model_package import (
    PackageError,
    _strict_json,
)
from portfolio_api.financial_model_package_exporter import (
    CONTRACT_VERSION as DCF_PACKAGE_VERSION,
)
from portfolio_api.financial_model_package_exporter import (
    DcfModelPackage,
    DcfPublishedOutputs,
    validate_dcf_model_package,
)
from portfolio_api.financial_models import (
    DcfCalculation,
    MarketPriceInput,
    calculate_ufcf_dcf,
)
from portfolio_api.return_semantics import (
    OWNER_CASH_FLOW_EQUITY_IRR,
    RESIDUAL_INCOME_EQUITY_IRR,
)

PACKAGE_VERSION: Literal["financial-model-package-v3"] = "financial-model-package-v3"
PACKAGE_ENGINE_VERSIONS: dict[
    str,
    Literal[
        "ufcf-dcf-package-engine-v1",
        "owner-cash-flow-package-engine-v1",
        "residual-income-package-engine-v1",
    ],
] = {
    "UFCF_DCF_10Y_FADE": "ufcf-dcf-package-engine-v1",
    "OWNER_CASH_FLOW_10Y": "owner-cash-flow-package-engine-v1",
    "RESIDUAL_INCOME_10Y_FADE": "residual-income-package-engine-v1",
}
PORTABLE_REPRESENTATIVE_MODELS: dict[
    str,
    tuple[
        Literal["OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"],
        Literal["USD", "INR"],
    ],
] = {
    "W-TOST": ("OWNER_CASH_FLOW_10Y", "USD"),
    "W-HDFC": ("RESIDUAL_INCOME_10Y_FADE", "INR"),
}


class StrictPackageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PackageIdentity(StrictPackageModel):
    source_model_key: str = Field(min_length=1, max_length=120)
    model_id: UUID | None
    company_id: UUID | None
    valuation_listing_id: UUID | None
    company_name: str | None
    listing_ticker: str | None
    listing_venue: str | None
    security_type: str | None
    listing_currency: str | None
    model_currency: str = Field(pattern=r"^[A-Z]{3}$")
    model_type: Literal["UFCF_DCF_10Y_FADE", "OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"]
    methodology_version: str = Field(min_length=1, max_length=100)
    return_methodology_code: Literal[
        "UFCF_ENTERPRISE_IRR",
        "UFCF_ENTERPRISE_HMODEL_IRR",
        "OWNER_CASH_FLOW_EQUITY_IRR",
        "RESIDUAL_INCOME_EQUITY_IRR",
    ]
    return_methodology_version: Literal[1] = 1

    @model_validator(mode="after")
    def identity_has_a_listing_basis(self) -> PackageIdentity:
        if self.listing_currency is not None and not _currency(self.listing_currency):
            raise ValueError("Listing currency must be an ISO currency code")
        if self.valuation_listing_id is None and not all(
            (self.listing_ticker, self.listing_venue, self.listing_currency)
        ):
            raise ValueError("A package requires a canonical listing ID or exact listing identity")
        return self


class PackageRevision(StrictPackageModel):
    base_revision_id: UUID | None
    source_revision_id: str = Field(min_length=1, max_length=200)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_at: datetime | None
    author_identity: str | None
    authored_at: datetime | None
    source_reference: str | None
    rationale: str | None
    acceptance_state: Literal["PROPOSAL_NOT_ACCEPTED"]

    @model_validator(mode="after")
    def timestamps_are_explicit(self) -> PackageRevision:
        for value in (self.effective_at, self.authored_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("Package revision timestamps must include a timezone")
        return self


class DcfPackageSource(StrictPackageModel):
    source_kind: Literal["GOOGLE_SHEETS_DCF_PACKAGE_V2"]
    source_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_observed_at: datetime
    package: DcfModelPackage

    @model_validator(mode="after")
    def observed_time_is_aware(self) -> DcfPackageSource:
        if self.source_observed_at.tzinfo is None or self.source_observed_at.utcoffset() is None:
            raise ValueError("Source observation time needs a timezone")
        return self


class AdditionalContractSource(StrictPackageModel):
    source_kind: Literal["ADDITIONAL_MODEL_PORTABLE_CONTRACT_V2"]
    source_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_observed_at: datetime
    source_identity_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    canonical_identity: schemas.FinancialModelContractIdentity
    contract: schemas.AdditionalModelPortableContractV2

    @model_validator(mode="after")
    def observed_time_is_aware(self) -> AdditionalContractSource:
        if self.source_observed_at.tzinfo is None or self.source_observed_at.utcoffset() is None:
            raise ValueError("Source observation time needs a timezone")
        return self


PackageSource = Annotated[
    DcfPackageSource | AdditionalContractSource, Field(discriminator="source_kind")
]


class DcfUnits(StrictPackageModel):
    operating_amounts: Literal["MODEL_CURRENCY_BILLIONS"]
    share_count: Literal["BILLIONS_OF_SHARES"]
    per_share_values: Literal["MODEL_CURRENCY_PER_LISTING_SHARE"]


class OwnerCashFlowUnits(StrictPackageModel):
    monetary_amounts: Literal["MODEL_CURRENCY_BILLIONS"]
    share_count: Literal["BILLIONS_OF_SHARES"]
    per_share_values: Literal["MODEL_CURRENCY_PER_LISTING_SHARE"]


class ResidualIncomeUnits(StrictPackageModel):
    book_value_and_income: Literal["MODEL_CURRENCY_PER_LISTING_SHARE"]
    payout_ratio: Literal["FRACTION"]
    share_count: None = None


class PackageCalculationOutputs(StrictPackageModel):
    calculation_status: Literal["COMPLETE", "PARTIAL"]
    model_currency: str = Field(pattern=r"^[A-Z]{3}$")
    return_methodology_code: str
    return_methodology_version: Literal[1] = 1
    calculation_price_basis: Literal["UNDATED_SOURCE_REFERENCE_FOR_PARITY_ONLY", "NOT_PROVIDED"]
    calculation_price: schemas.ModelNumber | None
    calculation_price_effective_at: datetime | None
    calculation_price_observation_id: UUID | None
    price_unavailable_reason: str | None
    irr_unavailable_reason: str | None
    bear_fv: schemas.ModelNumber
    base_fv: schemas.ModelNumber
    bull_fv: schemas.ModelNumber
    bear_probability: schemas.Probability
    base_probability: schemas.Probability
    bull_probability: schemas.Probability
    weighted_fv: schemas.ModelNumber
    weighted_upside: schemas.ModelNumber | None
    expected_cash_flow_irr: schemas.ModelNumber | None
    hurdle: schemas.ModelNumber
    expected_excess: schemas.ModelNumber | None
    forward_fundamental_cagr: None = None

    @model_validator(mode="after")
    def outputs_match_price_basis(self) -> PackageCalculationOutputs:
        if self.calculation_price_basis == "NOT_PROVIDED":
            if any(
                value is not None
                for value in (
                    self.calculation_price,
                    self.calculation_price_effective_at,
                    self.calculation_price_observation_id,
                    self.weighted_upside,
                    self.expected_cash_flow_irr,
                    self.expected_excess,
                )
            ):
                raise ValueError("Price-dependent outputs require a declared price basis")
            if (
                self.calculation_status != "PARTIAL"
                or self.price_unavailable_reason is None
                or self.irr_unavailable_reason is None
            ):
                raise ValueError("Missing-price outputs must remain explicitly partial")
        elif (
            self.calculation_price is None
            or self.calculation_price <= 0
            or self.calculation_price_effective_at is not None
            or self.calculation_price_observation_id is not None
        ):
            raise ValueError("The source parity price must remain explicitly undated")
        return self


class DcfNativeOutputs(StrictPackageModel):
    engine_version: Literal["ufcf-dcf-package-engine-v1"]
    outputs: PackageCalculationOutputs
    projections: tuple[schemas.DcfProjectionCalculationPreviewRead, ...] = Field(
        min_length=30, max_length=30
    )


class OwnerCashFlowNativeOutputs(StrictPackageModel):
    engine_version: Literal["owner-cash-flow-package-engine-v1"]
    outputs: PackageCalculationOutputs
    projections: tuple[schemas.OwnerCashFlowProjectionRead, ...] = Field(
        min_length=30, max_length=30
    )


class ResidualIncomeNativeOutputs(StrictPackageModel):
    engine_version: Literal["residual-income-package-engine-v1"]
    outputs: PackageCalculationOutputs
    projections: tuple[schemas.ResidualIncomeProjectionRead, ...] = Field(
        min_length=30, max_length=30
    )


class DcfMethodPayload(StrictPackageModel):
    model_type: Literal["UFCF_DCF_10Y_FADE"]
    methodology_version: Literal["ufcf-dcf-fade-v1", "ufcf-dcf-explicit-tail-v1"]
    input_contract_version: Literal["DcfCalculationInput-v1"]
    units: DcfUnits
    inputs: schemas.DcfCalculationInput
    published_outputs: DcfPublishedOutputs
    native_outputs: DcfNativeOutputs


class OwnerPublishedOutputReference(StrictPackageModel):
    source_role: Literal["HISTORICAL_LEGACY_OUTPUT_NOT_CANDIDATE_CALCULATION"]
    snapshot: schemas.ModelOutputSnapshotRead


class OwnerCashFlowMethodPayload(StrictPackageModel):
    model_type: Literal["OWNER_CASH_FLOW_10Y"]
    methodology_version: Literal["owner-cash-flow-10y-v1"]
    input_contract_version: Literal["OwnerCashFlowInput-v1"]
    units: OwnerCashFlowUnits
    inputs: schemas.OwnerCashFlowInput
    published_output_reference: OwnerPublishedOutputReference | None
    native_outputs: OwnerCashFlowNativeOutputs


class ResidualIncomePublishedOutputReference(StrictPackageModel):
    source_role: Literal["HISTORICAL_LEGACY_OUTPUT_NOT_CANDIDATE_CALCULATION"]
    snapshot: schemas.ModelOutputSnapshotRead


class ResidualIncomeMethodPayload(StrictPackageModel):
    model_type: Literal["RESIDUAL_INCOME_10Y_FADE"]
    methodology_version: Literal["residual-income-10y-fade-v1"]
    input_contract_version: Literal["ResidualIncomeInput-v1"]
    units: ResidualIncomeUnits
    inputs: schemas.ResidualIncomeInput
    published_output_reference: ResidualIncomePublishedOutputReference | None
    native_outputs: ResidualIncomeNativeOutputs


PackageMethod = Annotated[
    DcfMethodPayload | OwnerCashFlowMethodPayload | ResidualIncomeMethodPayload,
    Field(discriminator="model_type"),
]


class MultiArchetypeFinancialModelPackage(StrictPackageModel):
    contract_version: Literal["financial-model-package-v3"]
    identity: PackageIdentity
    revision: PackageRevision
    source: PackageSource
    method: PackageMethod

    @model_validator(mode="after")
    def validate_shared_contract_links(self) -> MultiArchetypeFinancialModelPackage:
        method_type = self.method.model_type
        if self.identity.model_type != method_type:
            raise ValueError("Shared identity model type must match the method payload")
        expected_return_methods = {
            "UFCF_DCF_10Y_FADE": {
                "UFCF_ENTERPRISE_IRR",
                "UFCF_ENTERPRISE_HMODEL_IRR",
            },
            "OWNER_CASH_FLOW_10Y": {OWNER_CASH_FLOW_EQUITY_IRR},
            "RESIDUAL_INCOME_10Y_FADE": {RESIDUAL_INCOME_EQUITY_IRR},
        }
        if self.identity.return_methodology_code not in expected_return_methods[method_type]:
            raise ValueError("Return methodology is incompatible with the valuation method")
        if self.method.methodology_version != self.identity.methodology_version:
            raise ValueError("Shared and method-specific methodology versions must match")
        inputs = self.method.inputs
        if _input_sha256(inputs) != self.revision.input_sha256:
            raise ValueError("Revision input digest does not match the method-specific inputs")
        if self.revision.acceptance_state != "PROPOSAL_NOT_ACCEPTED":
            raise ValueError("A source package cannot represent an accepted model revision")
        _validate_source_and_identity(self)
        return self


@dataclass(frozen=True)
class MultiArchetypePackageValidation:
    package: MultiArchetypeFinancialModelPackage
    payload_sha256: str
    replay_status: Literal["REPLAY_PASS"]


class _ProjectionIdentity(Protocol):
    scenario: DcfScenario
    forecast_year: int


def _currency(value: str) -> bool:
    return len(value) == 3 and value.isascii() and value.isalpha() and value.isupper()


def _canonical_model(value: BaseModel) -> str:
    return _strict_json(value.model_dump(mode="json"))


def _input_sha256(inputs: BaseModel) -> str:
    return hashlib.sha256(_canonical_model(inputs).encode("utf-8")).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source_sha256(value: BaseModel) -> str:
    return _hash_bytes(_canonical_model(value).encode("utf-8"))


def package_sha256(package: MultiArchetypeFinancialModelPackage) -> str:
    return _hash_bytes(_canonical_model(package).encode("utf-8"))


def parse_model_package_v3(payload: str | bytes) -> MultiArchetypeFinancialModelPackage:
    """Parse the canonical decimal-string JSON representation of a v3 package.

    Pydantic's strict Python-mode contract accepts Decimal instances, while the
    package serializer intentionally emits exact decimal strings. JSON parsing
    permits those strings, then compares the canonical parsed form with the
    original JSON structure. This rejects any other type coercion; domain
    Decimal fields also reject binary floating-point values via `exact`.
    """
    package = MultiArchetypeFinancialModelPackage.model_validate_json(payload, strict=False)
    try:
        source_value = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Model package JSON is malformed") from exc
    if _strict_json(source_value) != _canonical_model(package):
        raise ValueError("Model package JSON must use its canonical typed representation")
    return package


def _validate_native_output_projections(
    projections: tuple[_ProjectionIdentity, ...],
) -> None:
    coverage = {(str(row.scenario.value), row.forecast_year) for row in projections}
    expected = {(scenario, year) for scenario in ("BEAR", "BASE", "BULL") for year in range(1, 11)}
    if coverage != expected:
        raise ValueError("Native method outputs require Bear/Base/Bull years 1 through 10")


def _round_api(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 60
        return value.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP)


def _native_summary(
    calculation: DcfCalculation | ArchetypeCalculation,
    *,
    model_currency: str,
    return_methodology_code: str,
    calculation_price_basis: Literal["UNDATED_SOURCE_REFERENCE_FOR_PARITY_ONLY", "NOT_PROVIDED"],
) -> PackageCalculationOutputs:
    return PackageCalculationOutputs(
        calculation_status=calculation.status,
        model_currency=model_currency,
        return_methodology_code=return_methodology_code,
        calculation_price_basis=calculation_price_basis,
        calculation_price=_round_api(calculation.current_price),
        calculation_price_effective_at=cast(datetime | None, calculation.price_effective_at),
        calculation_price_observation_id=calculation.price_observation_id,
        price_unavailable_reason=calculation.price_unavailable_reason,
        irr_unavailable_reason=calculation.irr_unavailable_reason,
        bear_fv=cast(Decimal, _round_api(calculation.bear_fv)),
        base_fv=cast(Decimal, _round_api(calculation.base_fv)),
        bull_fv=cast(Decimal, _round_api(calculation.bull_fv)),
        bear_probability=cast(Decimal, _round_api(calculation.bear_probability)),
        base_probability=cast(Decimal, _round_api(calculation.base_probability)),
        bull_probability=cast(Decimal, _round_api(calculation.bull_probability)),
        weighted_fv=cast(Decimal, _round_api(calculation.weighted_fv)),
        weighted_upside=_round_api(calculation.weighted_upside),
        expected_cash_flow_irr=_round_api(calculation.expected_cash_flow_irr),
        hurdle=cast(Decimal, _round_api(calculation.hurdle)),
        expected_excess=_round_api(calculation.expected_excess),
    )


def _dcf_native_outputs(
    package: DcfModelPackage,
    *,
    return_methodology_code: str,
) -> DcfNativeOutputs:
    price = package.published_outputs.parity_reference_price
    calculation = calculate_ufcf_dcf(
        package.inputs,
        model_currency=package.identity.model_currency,
        market_price=MarketPriceInput(
            observation_id=None,
            price=price,
            currency=package.identity.model_currency,
            effective_at=None,
            freshness="FRESH",
        ),
        return_methodology_code=return_methodology_code,
    )
    projection_fields = (
        "scenario",
        "forecast_year",
        "revenue",
        "ebit",
        "nopat",
        "depreciation_amortization",
        "capex",
        "net_working_capital",
        "change_in_nwc",
        "unlevered_free_cash_flow",
        "revenue_growth",
        "discount_rate",
        "discount_factor",
        "present_value_ufcf",
        "terminal_value",
    )
    projections = tuple(
        schemas.DcfProjectionCalculationPreviewRead.model_validate(
            {
                name: (
                    _round_api(value)
                    if isinstance(value := getattr(projection, name), Decimal)
                    else value
                )
                for name in projection_fields
            }
        )
        for scenario in calculation.scenarios
        for projection in scenario.projections
    )
    _validate_native_output_projections(projections)
    return DcfNativeOutputs(
        engine_version=cast(
            Literal["ufcf-dcf-package-engine-v1"],
            PACKAGE_ENGINE_VERSIONS["UFCF_DCF_10Y_FADE"],
        ),
        outputs=_native_summary(
            calculation,
            model_currency=package.identity.model_currency,
            return_methodology_code=return_methodology_code,
            calculation_price_basis="UNDATED_SOURCE_REFERENCE_FOR_PARITY_ONLY",
        ),
        projections=projections,
    )


def _archetype_native_outputs(
    model_type: Literal["OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"],
    inputs: schemas.OwnerCashFlowInput | schemas.ResidualIncomeInput,
    *,
    model_currency: str,
) -> OwnerCashFlowNativeOutputs | ResidualIncomeNativeOutputs:
    no_price = MarketPriceInput(None, None, model_currency, None, "NO_DATA")
    if model_type == "OWNER_CASH_FLOW_10Y":
        if not isinstance(inputs, schemas.OwnerCashFlowInput):
            raise PackageError(
                "PACKAGE_METHOD_INPUT_MISMATCH", "Owner cash-flow inputs are required."
            )
        calculation = calculate_owner_cash_flow(
            inputs, model_currency=model_currency, market_price=no_price
        )
        owner_projections = tuple(
            schemas.OwnerCashFlowProjectionRead(
                scenario=projection.scenario,
                forecast_year=projection.forecast_year,
                revenue=cast(Decimal, _round_api(projection.revenue)),
                owner_cash_flow=cast(Decimal, _round_api(projection.owner_cash_flow)),
                owner_cash_flow_per_share=cast(
                    Decimal, _round_api(projection.owner_cash_flow_per_share)
                ),
                present_value_per_share=cast(
                    Decimal, _round_api(projection.present_value_per_share)
                ),
                terminal_value_per_share=_round_api(projection.terminal_value_per_share),
            )
            for scenario in calculation.scenarios
            for projection in scenario.projections
            if isinstance(projection, OwnerCashFlowProjectionCalculation)
        )
        _validate_native_output_projections(owner_projections)
        return OwnerCashFlowNativeOutputs(
            engine_version=cast(
                Literal["owner-cash-flow-package-engine-v1"],
                PACKAGE_ENGINE_VERSIONS[model_type],
            ),
            outputs=_native_summary(
                calculation,
                model_currency=model_currency,
                return_methodology_code=OWNER_CASH_FLOW_EQUITY_IRR,
                calculation_price_basis="NOT_PROVIDED",
            ),
            projections=owner_projections,
        )

    if not isinstance(inputs, schemas.ResidualIncomeInput):
        raise PackageError("PACKAGE_METHOD_INPUT_MISMATCH", "Residual-income inputs are required.")
    calculation = calculate_residual_income(
        inputs, model_currency=model_currency, market_price=no_price
    )
    residual_projections = tuple(
        schemas.ResidualIncomeProjectionRead(
            scenario=projection.scenario,
            forecast_year=projection.forecast_year,
            beginning_book_value_per_share=cast(
                Decimal, _round_api(projection.beginning_book_value_per_share)
            ),
            return_on_equity=cast(Decimal, _round_api(projection.return_on_equity)),
            net_income_per_share=cast(Decimal, _round_api(projection.net_income_per_share)),
            dividend_per_share=cast(Decimal, _round_api(projection.dividend_per_share)),
            ending_book_value_per_share=cast(
                Decimal, _round_api(projection.ending_book_value_per_share)
            ),
            residual_income_per_share=cast(
                Decimal, _round_api(projection.residual_income_per_share)
            ),
            present_value_residual_income=cast(
                Decimal, _round_api(projection.present_value_residual_income)
            ),
            terminal_value_per_share=_round_api(projection.terminal_value_per_share),
        )
        for scenario in calculation.scenarios
        for projection in scenario.projections
        if isinstance(projection, ResidualIncomeProjectionCalculation)
    )
    _validate_native_output_projections(residual_projections)
    return ResidualIncomeNativeOutputs(
        engine_version=cast(
            Literal["residual-income-package-engine-v1"],
            PACKAGE_ENGINE_VERSIONS[model_type],
        ),
        outputs=_native_summary(
            calculation,
            model_currency=model_currency,
            return_methodology_code=RESIDUAL_INCOME_EQUITY_IRR,
            calculation_price_basis="NOT_PROVIDED",
        ),
        projections=residual_projections,
    )


def _validate_published_reference(
    snapshot: schemas.ModelOutputSnapshotRead | None,
    *,
    model_key: str,
    model_type: str,
    company_id: UUID,
    currency: str,
    method_code: str,
) -> None:
    if snapshot is None:
        return
    if (
        snapshot.model_key != model_key
        or snapshot.company_id != company_id
        or snapshot.model_currency != currency
        or snapshot.return_methodology_status != "CLASSIFIED"
        or snapshot.return_methodology is None
        or snapshot.return_methodology.code != method_code
        or snapshot.return_methodology.version != 1
    ):
        raise PackageError(
            "PACKAGE_PUBLISHED_OUTPUT_IDENTITY_MISMATCH",
            "The historical published output does not match model identity and methodology.",
        )
    expected_model_type = PORTABLE_REPRESENTATIVE_MODELS.get(model_key, (None, None))[0]
    if expected_model_type != model_type:
        raise PackageError(
            "PACKAGE_PUBLISHED_OUTPUT_METHOD_MISMATCH",
            "The historical output method differs from the package method.",
        )


def _validate_source_and_identity(package: MultiArchetypeFinancialModelPackage) -> None:
    identity = package.identity
    method = package.method
    source = package.source
    if isinstance(source, DcfPackageSource):
        source_package = source.package
        if (
            source_package.contract_version != DCF_PACKAGE_VERSION
            or source.source_payload_sha256 != _source_sha256(source_package)
            or method.model_type != "UFCF_DCF_10Y_FADE"
            or identity.source_model_key != source_package.identity.source_model_key
            or identity.company_id is not None
            or identity.valuation_listing_id is not None
            or identity.company_name != source_package.identity.company_name
            or identity.listing_ticker != source_package.identity.listing_ticker
            or identity.listing_venue != source_package.identity.listing_venue
            or identity.security_type != source_package.identity.security_type
            or identity.listing_currency != source_package.identity.listing_currency
            or identity.model_currency != source_package.identity.model_currency
            or identity.methodology_version != source_package.identity.methodology_version
            or identity.return_methodology_code != source_package.identity.return_methodology_code
            or method.methodology_version != source_package.identity.methodology_version
            or method.inputs.model_dump(mode="json")
            != source_package.inputs.model_dump(mode="json")
            or method.published_outputs.model_dump(mode="json")
            != source_package.published_outputs.model_dump(mode="json")
            or package.revision.source_revision_id != source_package.revision.external_revision_id
            or package.revision.base_revision_id != source_package.revision.base_revision_id
        ):
            raise ValueError("DCF method payload does not match its direct-Sheets source package")
        return

    contract = source.contract
    canonical_identity = source.canonical_identity
    representative = PORTABLE_REPRESENTATIVE_MODELS.get(contract.source_model_key or "")
    expected_source_reference = (
        contract.proposal.source_reference
        if contract.proposal
        else contract.candidate_revision.source
    )
    if (
        source.source_payload_sha256 != _source_sha256(contract)
        or representative is None
        or representative != (contract.model_type, contract.model_currency)
        or identity.source_model_key != contract.source_model_key
        or identity.model_id != contract.model_id
        or identity.company_id != contract.company_id
        or identity.valuation_listing_id != contract.valuation_listing_id
        or canonical_identity.model_id != contract.model_id
        or canonical_identity.company_id != contract.company_id
        or canonical_identity.model_type != contract.model_type
        or canonical_identity.valuation_listing_id != contract.valuation_listing_id
        or canonical_identity.valuation_listing.id != contract.valuation_listing_id
        or canonical_identity.model_currency != contract.model_currency
        or canonical_identity.source_model_key != contract.source_model_key
        or identity.model_currency != contract.model_currency
        or identity.listing_currency != canonical_identity.valuation_listing.currency
        or identity.listing_ticker != canonical_identity.valuation_listing.ticker
        or identity.listing_venue != canonical_identity.valuation_listing.venue
        or identity.model_type != contract.model_type
        or package.revision.base_revision_id != contract.base_revision_id
        or package.revision.source_revision_id != contract.candidate_revision.source_revision_id
        or package.revision.effective_at != contract.candidate_revision.effective_at
        or package.revision.rationale != contract.candidate_revision.rationale
        or package.revision.source_reference != expected_source_reference
        or not package.revision.rationale
        or not package.revision.rationale.strip()
        or not expected_source_reference
        or not expected_source_reference.strip()
    ):
        raise ValueError("Additional-model payload does not match its portable source contract")
    if isinstance(method, OwnerCashFlowMethodPayload):
        candidate_input = contract.candidate_revision.owner_cash_flow
        if (
            contract.model_type != "OWNER_CASH_FLOW_10Y"
            or candidate_input is None
            or method.inputs.model_dump(mode="json") != candidate_input.model_dump(mode="json")
            or identity.methodology_version != "owner-cash-flow-10y-v1"
            or identity.return_methodology_code != OWNER_CASH_FLOW_EQUITY_IRR
            or package.revision.author_identity
            != (contract.proposal.author_id if contract.proposal else None)
            or package.revision.authored_at
            != (contract.proposal.authored_at if contract.proposal else None)
        ):
            raise ValueError("Owner cash-flow package differs from its typed source contract")
        if method.published_output_reference is not None:
            _validate_published_reference(
                method.published_output_reference.snapshot,
                model_key=contract.source_model_key or "",
                model_type=contract.model_type,
                company_id=contract.company_id,
                currency=contract.model_currency,
                method_code=OWNER_CASH_FLOW_EQUITY_IRR,
            )
    elif isinstance(method, ResidualIncomeMethodPayload):
        candidate_residual_input = contract.candidate_revision.residual_income
        if (
            contract.model_type != "RESIDUAL_INCOME_10Y_FADE"
            or candidate_residual_input is None
            or method.inputs.model_dump(mode="json")
            != candidate_residual_input.model_dump(mode="json")
            or identity.methodology_version != "residual-income-10y-fade-v1"
            or identity.return_methodology_code != RESIDUAL_INCOME_EQUITY_IRR
            or package.revision.author_identity
            != (contract.proposal.author_id if contract.proposal else None)
            or package.revision.authored_at
            != (contract.proposal.authored_at if contract.proposal else None)
        ):
            raise ValueError("Residual-income package differs from its typed source contract")
        if method.published_output_reference is not None:
            _validate_published_reference(
                method.published_output_reference.snapshot,
                model_key=contract.source_model_key or "",
                model_type=contract.model_type,
                company_id=contract.company_id,
                currency=contract.model_currency,
                method_code=RESIDUAL_INCOME_EQUITY_IRR,
            )
    else:
        raise ValueError("The selected native valuation method is unsupported")


def build_package_from_dcf_v2(
    source_package: DcfModelPackage,
    *,
    source_payload_sha256: str,
    source_observed_at: datetime,
) -> MultiArchetypeFinancialModelPackage:
    """Wrap a reviewed direct-Sheets DCF package without changing its inputs."""
    if source_observed_at.tzinfo is None or source_observed_at.utcoffset() is None:
        raise PackageError(
            "PACKAGE_SOURCE_TIME_INVALID", "Source observation time needs a timezone."
        )
    if source_payload_sha256 != _source_sha256(source_package):
        raise PackageError(
            "PACKAGE_SOURCE_HASH_MISMATCH", "The source DCF package hash is invalid."
        )
    if source_package.identity.listing_currency != source_package.identity.model_currency:
        raise PackageError(
            "PACKAGE_CURRENCY_BASIS_UNSUPPORTED",
            "The reviewed DCF package requires listing and model currencies to match.",
        )
    validation = validate_dcf_model_package(
        source_package, source_payload_sha256, validated_at=source_observed_at
    )
    if validation.parity_report.get("status") != "PARITY_PASS":
        raise PackageError(
            "PACKAGE_SOURCE_PARITY_FAILED", "The DCF source package did not pass parity."
        )
    method_code = source_package.identity.return_methodology_code
    native = _dcf_native_outputs(source_package, return_methodology_code=method_code)
    identity = PackageIdentity(
        source_model_key=source_package.identity.source_model_key,
        model_id=None,
        company_id=None,
        valuation_listing_id=None,
        company_name=source_package.identity.company_name,
        listing_ticker=source_package.identity.listing_ticker,
        listing_venue=source_package.identity.listing_venue,
        security_type=source_package.identity.security_type,
        listing_currency=source_package.identity.listing_currency,
        model_currency=source_package.identity.model_currency,
        model_type=source_package.identity.model_type,
        methodology_version=source_package.identity.methodology_version,
        return_methodology_code=method_code,
    )
    inputs_digest = _input_sha256(source_package.inputs)
    package = MultiArchetypeFinancialModelPackage(
        contract_version=PACKAGE_VERSION,
        identity=identity,
        revision=PackageRevision(
            base_revision_id=source_package.revision.base_revision_id,
            source_revision_id=source_package.revision.external_revision_id,
            input_sha256=inputs_digest,
            effective_at=None,
            author_identity=None,
            authored_at=None,
            source_reference=None,
            rationale=None,
            acceptance_state="PROPOSAL_NOT_ACCEPTED",
        ),
        source=DcfPackageSource(
            source_kind="GOOGLE_SHEETS_DCF_PACKAGE_V2",
            source_payload_sha256=source_payload_sha256,
            source_observed_at=source_observed_at,
            package=source_package,
        ),
        method=DcfMethodPayload(
            model_type="UFCF_DCF_10Y_FADE",
            methodology_version=source_package.identity.methodology_version,
            input_contract_version="DcfCalculationInput-v1",
            units=DcfUnits(
                operating_amounts="MODEL_CURRENCY_BILLIONS",
                share_count="BILLIONS_OF_SHARES",
                per_share_values="MODEL_CURRENCY_PER_LISTING_SHARE",
            ),
            inputs=source_package.inputs,
            published_outputs=source_package.published_outputs,
            native_outputs=native,
        ),
    )
    return package


def build_package_from_additional_contract(
    contract: schemas.AdditionalModelPortableContractV2,
    *,
    canonical_identity: schemas.FinancialModelContractIdentity,
    source_observed_at: datetime,
    source_identity_sha256: str | None = None,
    published_output_snapshot: schemas.ModelOutputSnapshotRead | None = None,
) -> MultiArchetypeFinancialModelPackage:
    """Adapt the existing portable owner/residual contract; never infer a layout."""
    if source_observed_at.tzinfo is None or source_observed_at.utcoffset() is None:
        raise PackageError(
            "PACKAGE_SOURCE_TIME_INVALID", "Source observation time needs a timezone."
        )
    model_key = contract.source_model_key or ""
    representative = PORTABLE_REPRESENTATIVE_MODELS.get(model_key)
    if representative is None:
        raise PackageError(
            "PACKAGE_TEMPLATE_UNSUPPORTED",
            "No reviewed representative source adapter supports this additional model key.",
        )
    model_type, expected_currency = representative
    if (contract.model_type, contract.model_currency) != (model_type, expected_currency):
        raise PackageError(
            "PACKAGE_TEMPLATE_IDENTITY_MISMATCH",
            "The source model key, method and currency do not match the reviewed adapter.",
        )
    if (
        canonical_identity.model_id != contract.model_id
        or canonical_identity.company_id != contract.company_id
        or canonical_identity.model_type != contract.model_type
        or canonical_identity.valuation_listing_id != contract.valuation_listing_id
        or canonical_identity.valuation_listing.id != contract.valuation_listing_id
        or canonical_identity.model_currency != contract.model_currency
        or canonical_identity.source_model_key != contract.source_model_key
    ):
        raise PackageError(
            "PACKAGE_CANONICAL_IDENTITY_MISMATCH",
            "The portable contract does not match the canonical model and listing identity.",
        )
    method_code = cast(
        Literal["OWNER_CASH_FLOW_EQUITY_IRR", "RESIDUAL_INCOME_EQUITY_IRR"],
        OWNER_CASH_FLOW_EQUITY_IRR
        if model_type == "OWNER_CASH_FLOW_10Y"
        else RESIDUAL_INCOME_EQUITY_IRR,
    )
    contract_hash = _source_sha256(contract)
    candidate = contract.candidate_revision
    if model_type == "OWNER_CASH_FLOW_10Y":
        if candidate.owner_cash_flow is None or candidate.residual_income is not None:
            raise PackageError(
                "PACKAGE_METHOD_INPUT_MISMATCH", "Owner cash-flow inputs are required."
            )
        _validate_published_reference(
            published_output_snapshot,
            model_key=model_key,
            model_type=model_type,
            company_id=contract.company_id,
            currency=contract.model_currency,
            method_code=method_code,
        )
        native = _archetype_native_outputs(
            cast(Literal["OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"], model_type),
            candidate.owner_cash_flow,
            model_currency=contract.model_currency,
        )
        if not isinstance(native, OwnerCashFlowNativeOutputs):
            raise PackageError(
                "PACKAGE_METHOD_OUTPUT_MISMATCH", "Owner cash-flow output type mismatch."
            )
        method: PackageMethod = OwnerCashFlowMethodPayload(
            model_type="OWNER_CASH_FLOW_10Y",
            methodology_version="owner-cash-flow-10y-v1",
            input_contract_version="OwnerCashFlowInput-v1",
            units=OwnerCashFlowUnits(
                monetary_amounts="MODEL_CURRENCY_BILLIONS",
                share_count="BILLIONS_OF_SHARES",
                per_share_values="MODEL_CURRENCY_PER_LISTING_SHARE",
            ),
            inputs=candidate.owner_cash_flow,
            published_output_reference=(
                OwnerPublishedOutputReference(
                    source_role="HISTORICAL_LEGACY_OUTPUT_NOT_CANDIDATE_CALCULATION",
                    snapshot=published_output_snapshot,
                )
                if published_output_snapshot
                else None
            ),
            native_outputs=native,
        )
    else:
        if candidate.residual_income is None or candidate.owner_cash_flow is not None:
            raise PackageError(
                "PACKAGE_METHOD_INPUT_MISMATCH", "Residual-income inputs are required."
            )
        _validate_published_reference(
            published_output_snapshot,
            model_key=model_key,
            model_type=model_type,
            company_id=contract.company_id,
            currency=contract.model_currency,
            method_code=method_code,
        )
        native = _archetype_native_outputs(
            cast(Literal["OWNER_CASH_FLOW_10Y", "RESIDUAL_INCOME_10Y_FADE"], model_type),
            candidate.residual_income,
            model_currency=contract.model_currency,
        )
        if not isinstance(native, ResidualIncomeNativeOutputs):
            raise PackageError(
                "PACKAGE_METHOD_OUTPUT_MISMATCH", "Residual-income output type mismatch."
            )
        method = ResidualIncomeMethodPayload(
            model_type="RESIDUAL_INCOME_10Y_FADE",
            methodology_version="residual-income-10y-fade-v1",
            input_contract_version="ResidualIncomeInput-v1",
            units=ResidualIncomeUnits(
                book_value_and_income="MODEL_CURRENCY_PER_LISTING_SHARE",
                payout_ratio="FRACTION",
            ),
            inputs=candidate.residual_income,
            published_output_reference=(
                ResidualIncomePublishedOutputReference(
                    source_role="HISTORICAL_LEGACY_OUTPUT_NOT_CANDIDATE_CALCULATION",
                    snapshot=published_output_snapshot,
                )
                if published_output_snapshot
                else None
            ),
            native_outputs=native,
        )
    input_contract = (
        cast(BaseModel, candidate.owner_cash_flow)
        if model_type == "OWNER_CASH_FLOW_10Y"
        else cast(BaseModel, candidate.residual_income)
    )
    package = MultiArchetypeFinancialModelPackage(
        contract_version=PACKAGE_VERSION,
        identity=PackageIdentity(
            source_model_key=model_key,
            model_id=contract.model_id,
            company_id=contract.company_id,
            valuation_listing_id=contract.valuation_listing_id,
            company_name=None,
            listing_ticker=canonical_identity.valuation_listing.ticker,
            listing_venue=canonical_identity.valuation_listing.venue,
            security_type=None,
            listing_currency=canonical_identity.valuation_listing.currency,
            model_currency=contract.model_currency,
            model_type=contract.model_type,
            methodology_version=(
                "owner-cash-flow-10y-v1"
                if model_type == "OWNER_CASH_FLOW_10Y"
                else "residual-income-10y-fade-v1"
            ),
            return_methodology_code=method_code,
        ),
        revision=PackageRevision(
            base_revision_id=contract.base_revision_id,
            source_revision_id=candidate.source_revision_id,
            input_sha256=_input_sha256(input_contract),
            effective_at=candidate.effective_at,
            author_identity=contract.proposal.author_id if contract.proposal else None,
            authored_at=contract.proposal.authored_at if contract.proposal else None,
            source_reference=(
                contract.proposal.source_reference if contract.proposal else candidate.source
            ),
            rationale=candidate.rationale,
            acceptance_state="PROPOSAL_NOT_ACCEPTED",
        ),
        source=AdditionalContractSource(
            source_kind="ADDITIONAL_MODEL_PORTABLE_CONTRACT_V2",
            source_payload_sha256=contract_hash,
            source_observed_at=source_observed_at,
            source_identity_sha256=source_identity_sha256,
            canonical_identity=canonical_identity,
            contract=contract,
        ),
        method=method,
    )
    return package


def validate_model_package_v3(
    package: MultiArchetypeFinancialModelPackage,
    expected_payload_sha256: str,
) -> MultiArchetypePackageValidation:
    if package_sha256(package) != expected_payload_sha256:
        raise PackageError("PACKAGE_HASH_MISMATCH", "The v3 model package hash is invalid.")
    _validate_source_and_identity(package)
    if _input_sha256(package.method.inputs) != package.revision.input_sha256:
        raise PackageError(
            "PACKAGE_INPUT_HASH_MISMATCH",
            "The method input digest does not match the immutable package revision.",
        )
    source = package.source
    method = package.method
    native: DcfNativeOutputs | OwnerCashFlowNativeOutputs | ResidualIncomeNativeOutputs
    if isinstance(method, DcfMethodPayload):
        if not isinstance(source, DcfPackageSource):
            raise PackageError(
                "PACKAGE_SOURCE_METHOD_MISMATCH", "The DCF method requires a DCF source package."
            )
        source_validation = validate_dcf_model_package(
            source.package,
            source.source_payload_sha256,
            validated_at=source.source_observed_at,
        )
        if source_validation.parity_report.get("status") != "PARITY_PASS":
            raise PackageError(
                "PACKAGE_SOURCE_PARITY_FAILED", "The DCF source package did not pass parity."
            )
        native = _dcf_native_outputs(
            source.package,
            return_methodology_code=package.identity.return_methodology_code,
        )
    elif isinstance(method, OwnerCashFlowMethodPayload):
        if not isinstance(source, AdditionalContractSource):
            raise PackageError(
                "PACKAGE_SOURCE_METHOD_MISMATCH",
                "The owner-cash-flow method requires its portable source contract.",
            )
        native = _archetype_native_outputs(
            "OWNER_CASH_FLOW_10Y", method.inputs, model_currency=package.identity.model_currency
        )
    else:
        if not isinstance(source, AdditionalContractSource):
            raise PackageError(
                "PACKAGE_SOURCE_METHOD_MISMATCH",
                "The residual-income method requires its portable source contract.",
            )
        native = _archetype_native_outputs(
            "RESIDUAL_INCOME_10Y_FADE",
            method.inputs,
            model_currency=package.identity.model_currency,
        )
    if native.model_dump(mode="json") != method.native_outputs.model_dump(mode="json"):
        raise PackageError(
            "PACKAGE_NATIVE_REPLAY_MISMATCH",
            "The method-specific native outputs differ from deterministic replay.",
        )
    return MultiArchetypePackageValidation(package, expected_payload_sha256, "REPLAY_PASS")
