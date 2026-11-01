"""Synthetic contract and engine replay tests for the multi-method package envelope."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

import pytest
from pydantic import ValidationError
from synthetic_financial_fixtures import owner_cash_flow_fixture, residual_income_fixture
from test_financial_model_package_exporter import (
    _fixture_package,
)

from portfolio_api.domain import schemas
from portfolio_api.financial_model_package import PackageError
from portfolio_api.financial_model_package_exporter import validate_dcf_model_package
from portfolio_api.financial_model_package_multi import (
    AdditionalContractSource,
    DcfMethodPayload,
    MultiArchetypeFinancialModelPackage,
    OwnerCashFlowMethodPayload,
    ResidualIncomeMethodPayload,
    _source_sha256,
    build_package_from_additional_contract,
    build_package_from_dcf_v2,
    package_sha256,
    parse_model_package_v3,
    validate_model_package_v3,
)

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
UUID_NAMESPACE = UUID("9c5d4aa0-30a9-4f77-a9d0-ec4af6c9f20e")


def _stable_uuid(value: str) -> UUID:
    return uuid5(UUID_NAMESPACE, value)


def _additional_contract(model_key: str) -> schemas.AdditionalModelPortableContractV2:
    if model_key == "W-TOST":
        fixture = owner_cash_flow_fixture()
        model_type = "OWNER_CASH_FLOW_10Y"
        currency = "USD"
        inputs = schemas.OwnerCashFlowInput.model_validate(fixture["input"])
        candidate = schemas.AdditionalModelContractCandidate(
            source_revision_id="fixture:W-TOST:revision-2",
            source="Synthetic contract fixture",
            rationale="Synthetic adapter contract; no investment decision is represented.",
            effective_at=NOW,
            owner_cash_flow=inputs,
        )
    else:
        fixture = residual_income_fixture()
        model_type = "RESIDUAL_INCOME_10Y_FADE"
        currency = "INR"
        residual_inputs = schemas.ResidualIncomeInput.model_validate(fixture["input"])
        candidate = schemas.AdditionalModelContractCandidate(
            source_revision_id="fixture:W-HDFC:revision-2",
            source="Synthetic contract fixture",
            rationale="Synthetic contract fixture; no investment decision is represented.",
            effective_at=NOW,
            residual_income=residual_inputs,
        )
    return schemas.AdditionalModelPortableContractV2(
        contract_version="2.0.0",
        exported_at=NOW,
        model_id=_stable_uuid(f"{model_key}:model"),
        company_id=_stable_uuid(f"{model_key}:company"),
        model_type=model_type,
        model_name=f"Synthetic {model_key} model contract",
        valuation_listing_id=_stable_uuid(f"{model_key}:listing"),
        model_currency=currency,
        source_model_key=model_key,
        base_revision_id=_stable_uuid(f"{model_key}:base-revision"),
        base_revision_number=1,
        candidate_revision=candidate,
    )


def _canonical_identity(
    contract: schemas.AdditionalModelPortableContractV2,
) -> schemas.FinancialModelContractIdentity:
    return schemas.FinancialModelContractIdentity(
        model_id=contract.model_id,
        company_id=contract.company_id,
        model_type=contract.model_type,
        model_name=contract.model_name,
        valuation_listing_id=contract.valuation_listing_id,
        valuation_listing=schemas.ListingRead(
            id=contract.valuation_listing_id,
            security_id=_stable_uuid(f"{contract.source_model_key}:security"),
            ticker="SYNTHETIC",
            venue="TEST",
            currency=contract.model_currency,
            identity_source_ref="fixture-only identity",
            is_demo=True,
        ),
        model_currency=contract.model_currency,
        source_model_key=contract.source_model_key,
    )


@pytest.mark.parametrize("model_key", ("W-TOST", "W-HDFC"))
def test_additional_model_adapters_keep_method_inputs_and_outputs_distinct(model_key: str) -> None:
    contract = _additional_contract(model_key)
    package = build_package_from_additional_contract(
        contract,
        canonical_identity=_canonical_identity(contract),
        source_observed_at=NOW,
        source_identity_sha256=hashlib.sha256(b"synthetic source identity").hexdigest(),
    )
    replay = validate_model_package_v3(package, package_sha256(package))

    assert replay.replay_status == "REPLAY_PASS"
    assert isinstance(package.source, AdditionalContractSource)
    assert package.source.contract.model_type == package.identity.model_type
    assert package.source.canonical_identity.valuation_listing_id == (
        package.identity.valuation_listing_id
    )
    assert package.identity.valuation_listing_id == contract.valuation_listing_id
    assert package.revision.base_revision_id == contract.base_revision_id
    assert package.revision.source_revision_id == contract.candidate_revision.source_revision_id
    assert package.revision.acceptance_state == "PROPOSAL_NOT_ACCEPTED"
    assert package.method.native_outputs.outputs.calculation_price_basis == "NOT_PROVIDED"
    assert package.method.native_outputs.outputs.expected_cash_flow_irr is None
    assert package.method.native_outputs.outputs.weighted_upside is None
    assert len(package.method.native_outputs.projections) == 30
    expected = (
        owner_cash_flow_fixture()["expected"]
        if model_key == "W-TOST"
        else residual_income_fixture()["expected"]
    )
    for field in (
        "bear_fv",
        "base_fv",
        "bull_fv",
        "weighted_fv",
        "hurdle",
    ):
        assert abs(
            getattr(package.method.native_outputs.outputs, field) - Decimal(expected[field])
        ) <= Decimal("0.000000000000000001"), field

    if model_key == "W-TOST":
        assert isinstance(package.method, OwnerCashFlowMethodPayload)
        assert package.method.units.monetary_amounts == "MODEL_CURRENCY_BILLIONS"
        assert package.method.published_output_reference is None
        assert abs(
            package.method.native_outputs.outputs.base_fv - Decimal("22.9710036999421021")
        ) <= Decimal("0.0000001")
    else:
        assert isinstance(package.method, ResidualIncomeMethodPayload)
        assert package.method.units.book_value_and_income == "MODEL_CURRENCY_PER_LISTING_SHARE"
        assert package.method.published_output_reference is None
        assert abs(
            package.method.native_outputs.outputs.base_fv - Decimal("30.7078459929566553")
        ) <= Decimal("0.0000001")

    round_trip = parse_model_package_v3(package.model_dump_json())
    assert round_trip == package
    assert validate_model_package_v3(round_trip, package_sha256(round_trip)).replay_status == (
        "REPLAY_PASS"
    )


def test_dcf_adapter_separates_published_reference_from_native_replay() -> None:
    source_package, source_hash = _fixture_package("P-GOOGL")
    # The pre-existing v2 contract remains independently valid and unchanged.
    assert (
        validate_dcf_model_package(source_package, source_hash, validated_at=NOW).parity_report[
            "status"
        ]
        == "PARITY_PASS"
    )
    package = build_package_from_dcf_v2(
        source_package,
        source_payload_sha256=source_hash,
        source_observed_at=NOW,
    )

    assert isinstance(package.method, DcfMethodPayload)
    assert package.method.published_outputs == source_package.published_outputs
    assert package.method.native_outputs.outputs.calculation_price_basis == (
        "UNDATED_SOURCE_REFERENCE_FOR_PARITY_ONLY"
    )
    assert package.method.native_outputs.outputs.calculation_price_effective_at is None
    assert package.method.native_outputs.outputs.expected_cash_flow_irr is not None
    assert package.method.input_contract_version == "DcfCalculationInput-v1"
    assert len(package.method.native_outputs.projections) == 30
    assert package.revision.acceptance_state == "PROPOSAL_NOT_ACCEPTED"
    assert validate_model_package_v3(package, package_sha256(package)).replay_status == (
        "REPLAY_PASS"
    )
    repeated = build_package_from_dcf_v2(
        source_package,
        source_payload_sha256=source_hash,
        source_observed_at=NOW,
    )
    assert package_sha256(repeated) == package_sha256(package)


def test_wrong_method_currency_or_unreviewed_source_key_is_rejected() -> None:
    owner_contract = _additional_contract("W-TOST")
    identity = _canonical_identity(owner_contract)
    wrong_currency = owner_contract.model_copy(update={"model_currency": "EUR"})
    with pytest.raises((PackageError, ValidationError, ValueError)):
        build_package_from_additional_contract(
            wrong_currency, canonical_identity=identity, source_observed_at=NOW
        )

    unknown_key = owner_contract.model_copy(update={"source_model_key": "W-UNKNOWN"})
    with pytest.raises(PackageError, match="No reviewed representative source adapter"):
        build_package_from_additional_contract(
            unknown_key, canonical_identity=identity, source_observed_at=NOW
        )

    wrong_method = owner_contract.model_copy(update={"model_type": "RESIDUAL_INCOME_10Y_FADE"})
    with pytest.raises((PackageError, ValidationError, ValueError)):
        build_package_from_additional_contract(
            wrong_method, canonical_identity=identity, source_observed_at=NOW
        )


def test_additional_model_adapter_rejects_mismatched_canonical_listing_identity() -> None:
    contract = _additional_contract("W-TOST")
    identity = _canonical_identity(contract).model_copy(
        update={"valuation_listing_id": _stable_uuid("unrelated listing")}
    )
    with pytest.raises(PackageError, match="canonical model and listing identity"):
        build_package_from_additional_contract(
            contract, canonical_identity=identity, source_observed_at=NOW
        )


def test_source_hash_and_method_input_tampering_fail_replay() -> None:
    contract = _additional_contract("W-HDFC")
    package = build_package_from_additional_contract(
        contract, canonical_identity=_canonical_identity(contract), source_observed_at=NOW
    )
    bad_source = package.source.model_copy(update={"source_payload_sha256": "0" * 64})
    tampered = package.model_copy(update={"source": bad_source})
    with pytest.raises(ValueError, match="portable source contract"):
        validate_model_package_v3(tampered, package_sha256(tampered))

    with pytest.raises(PackageError, match="hash"):
        validate_model_package_v3(package, "0" * 64)


def test_package_replay_is_idempotent_and_proposal_does_not_accept_revision() -> None:
    contract = _additional_contract("W-TOST")
    identity = _canonical_identity(contract)
    first = build_package_from_additional_contract(
        contract, canonical_identity=identity, source_observed_at=NOW
    )
    second = build_package_from_additional_contract(
        contract, canonical_identity=identity, source_observed_at=NOW
    )
    assert package_sha256(first) == package_sha256(second)
    assert validate_model_package_v3(first, package_sha256(first)).replay_status == "REPLAY_PASS"
    assert first.revision.acceptance_state == "PROPOSAL_NOT_ACCEPTED"


def test_package_json_uses_exact_decimal_strings_and_rejects_float_values() -> None:
    contract = _additional_contract("W-HDFC")
    package = build_package_from_additional_contract(
        contract, canonical_identity=_canonical_identity(contract), source_observed_at=NOW
    )
    payload = package.model_dump_json()
    assert '"base_fv":"30.707845992956655293"' in payload
    assert parse_model_package_v3(payload) == package

    parsed = json.loads(payload)
    parsed["method"]["native_outputs"]["outputs"]["base_fv"] = 30.7078
    with pytest.raises(ValidationError):
        parse_model_package_v3(json.dumps(parsed))

    parsed = json.loads(payload)
    parsed["identity"]["listing_ticker"] = 123
    with pytest.raises((ValidationError, ValueError)):
        parse_model_package_v3(json.dumps(parsed))


def test_v3_rejects_unsupported_package_version_and_missing_rationale() -> None:
    contract = _additional_contract("W-TOST")
    package = build_package_from_additional_contract(
        contract, canonical_identity=_canonical_identity(contract), source_observed_at=NOW
    )
    payload = package.model_dump(mode="json")
    payload["contract_version"] = "financial-model-package-v4"
    with pytest.raises(ValidationError):
        MultiArchetypeFinancialModelPackage.model_validate(payload)

    candidate = contract.candidate_revision.model_copy(update={"rationale": None})
    incomplete = contract.model_copy(update={"candidate_revision": candidate})
    with pytest.raises(ValueError, match="portable source contract"):
        build_package_from_additional_contract(
            incomplete, canonical_identity=_canonical_identity(contract), source_observed_at=NOW
        )


def test_dcf_package_rejects_listing_model_currency_mismatch() -> None:
    package, _ = _fixture_package("P-GOOGL")
    identity = package.identity.model_copy(update={"listing_currency": "EUR"})
    changed_source = package.model_copy(update={"identity": identity})
    changed_hash = _source_sha256(changed_source)
    with pytest.raises(PackageError, match="listing and model currencies"):
        build_package_from_dcf_v2(
            changed_source,
            source_payload_sha256=changed_hash,
            source_observed_at=NOW,
        )
