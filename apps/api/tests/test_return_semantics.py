from portfolio_api.return_semantics import (
    OWNER_CASH_FLOW_EQUITY_IRR,
    RESIDUAL_INCOME_EQUITY_IRR,
    UFCF_ENTERPRISE_HMODEL_IRR,
    UFCF_ENTERPRISE_IRR,
    VERIFIED_LEGACY_METHOD_BY_MODEL_KEY,
    ReturnBasis,
    classify_comparability,
    has_comparable_observation_basis,
)


def test_same_versioned_method_is_directly_comparable_and_fx_is_explicit() -> None:
    usd = ReturnBasis(UFCF_ENTERPRISE_IRR, 1, "USD")
    eur = ReturnBasis(UFCF_ENTERPRISE_IRR, 1, "EUR")
    assert classify_comparability(usd, usd) == "DIRECT"
    assert classify_comparability(usd, eur) == "DIRECT_FX_EXCLUDED"


def test_equity_methods_are_conditionally_comparable_but_not_enterprise_methods() -> None:
    owner = ReturnBasis(OWNER_CASH_FLOW_EQUITY_IRR, 1, "USD")
    residual_income = ReturnBasis(RESIDUAL_INCOME_EQUITY_IRR, 1, "USD")
    enterprise = ReturnBasis(UFCF_ENTERPRISE_IRR, 1, "USD")
    assert classify_comparability(owner, residual_income) == "CONDITIONAL_EQUITY"
    assert classify_comparability(enterprise, owner) == "NOT_COMPARABLE_PERSPECTIVE"


def test_legacy_h_model_terminal_return_is_separate_from_standard_ufcf_return() -> None:
    standard = ReturnBasis(UFCF_ENTERPRISE_IRR, 1, "USD")
    h_model = ReturnBasis(UFCF_ENTERPRISE_HMODEL_IRR, 1, "USD")
    assert classify_comparability(h_model, h_model) == "DIRECT"
    assert classify_comparability(standard, h_model) == "NOT_COMPARABLE_METHOD"


def test_method_version_and_unknown_method_do_not_claim_comparability() -> None:
    current = ReturnBasis(OWNER_CASH_FLOW_EQUITY_IRR, 1, "USD")
    future = ReturnBasis(OWNER_CASH_FLOW_EQUITY_IRR, 2, "USD")
    unclassified = ReturnBasis(None, None, "USD")
    assert classify_comparability(current, future) == "NOT_COMPARABLE_VERSION"
    assert classify_comparability(current, unclassified) == "UNKNOWN_METHOD"
    assert (
        classify_comparability(
            ReturnBasis(OWNER_CASH_FLOW_EQUITY_IRR, 2, "USD"),
            ReturnBasis(OWNER_CASH_FLOW_EQUITY_IRR, 2, "USD"),
        )
        == "NOT_COMPARABLE_VERSION"
    )


def test_return_observation_requires_listing_identity_and_captured_quote_basis() -> None:
    captured = ReturnBasis(
        UFCF_ENTERPRISE_IRR,
        1,
        "USD",
        listing_id="listing-googl",
        share_price_basis_status="CAPTURED",
    )
    unretained_legacy = ReturnBasis(
        UFCF_ENTERPRISE_IRR,
        1,
        "USD",
        listing_id="listing-googl",
        share_price_basis_status="NOT_RETAINED",
    )
    ambiguous_listing = ReturnBasis(
        UFCF_ENTERPRISE_IRR,
        1,
        "USD",
        listing_id=None,
        share_price_basis_status="CAPTURED",
    )

    assert has_comparable_observation_basis(captured)
    assert not has_comparable_observation_basis(unretained_legacy)
    assert not has_comparable_observation_basis(ambiguous_listing)


def test_legacy_assignment_requires_an_explicitly_documented_tab() -> None:
    assert VERIFIED_LEGACY_METHOD_BY_MODEL_KEY["P-GOOGL"] == UFCF_ENTERPRISE_IRR
    assert VERIFIED_LEGACY_METHOD_BY_MODEL_KEY["P-AMZN"] == UFCF_ENTERPRISE_HMODEL_IRR
    assert VERIFIED_LEGACY_METHOD_BY_MODEL_KEY["P-HIMS"] == UFCF_ENTERPRISE_HMODEL_IRR
    assert VERIFIED_LEGACY_METHOD_BY_MODEL_KEY["P-MSFT"] == UFCF_ENTERPRISE_IRR
    assert VERIFIED_LEGACY_METHOD_BY_MODEL_KEY["W-TOST"] == OWNER_CASH_FLOW_EQUITY_IRR
    assert VERIFIED_LEGACY_METHOD_BY_MODEL_KEY["W-HDFC"] == RESIDUAL_INCOME_EQUITY_IRR
    assert "W-NU" not in VERIFIED_LEGACY_METHOD_BY_MODEL_KEY
