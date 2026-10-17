"""Versioned return definitions and explicit comparability rules.

These definitions document the supported methodologies; they do not recalculate or
translate returns. In particular, an enterprise UFCF return cannot be converted to
an equity return without future financing and shareholder-distribution assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

UFCF_ENTERPRISE_IRR = "UFCF_ENTERPRISE_IRR"
UFCF_ENTERPRISE_HMODEL_IRR = "UFCF_ENTERPRISE_HMODEL_IRR"
OWNER_CASH_FLOW_EQUITY_IRR = "OWNER_CASH_FLOW_EQUITY_IRR"
RESIDUAL_INCOME_EQUITY_IRR = "RESIDUAL_INCOME_EQUITY_IRR"

NATIVE_METHOD_BY_MODEL_TYPE = {
    "UFCF_DCF_10Y_FADE": UFCF_ENTERPRISE_IRR,
    "OWNER_CASH_FLOW_10Y": OWNER_CASH_FLOW_EQUITY_IRR,
    "RESIDUAL_INCOME_10Y_FADE": RESIDUAL_INCOME_EQUITY_IRR,
}

# Method assignment for imported outputs is deliberately narrower than the
# inventory's title-based classifications. These are the model tabs with an
# explicit source-method/parity reference in the migration evidence.
VERIFIED_LEGACY_METHOD_BY_MODEL_KEY = {
    "P-GOOGL": UFCF_ENTERPRISE_IRR,
    "P-ASML": UFCF_ENTERPRISE_IRR,
    "P-ISRG": UFCF_ENTERPRISE_IRR,
    "P-MA": UFCF_ENTERPRISE_IRR,
    "P-CPRT": UFCF_ENTERPRISE_IRR,
    "P-UBER": UFCF_ENTERPRISE_IRR,
    "P-AMZN": UFCF_ENTERPRISE_HMODEL_IRR,
    "P-HIMS": UFCF_ENTERPRISE_HMODEL_IRR,
    "P-MSFT": UFCF_ENTERPRISE_IRR,
    "W-TOST": OWNER_CASH_FLOW_EQUITY_IRR,
    "W-HDFC": RESIDUAL_INCOME_EQUITY_IRR,
}


@dataclass(frozen=True)
class ReturnMethodology:
    code: str
    title: str
    version: int
    cash_flow_basis: str
    perspective: str
    entry_value_basis: str
    share_price_basis: str
    comparability_group: str
    cross_method_policy: str
    limitation: str


DEFINITIONS = (
    ReturnMethodology(
        code=UFCF_ENTERPRISE_IRR,
        title="Probability-weighted enterprise UFCF IRR",
        version=1,
        cash_flow_basis=(
            "Probability-weighted annual unlevered free cash flow plus terminal enterprise value."
        ),
        perspective="ENTERPRISE",
        entry_value_basis=(
            "Exact listing share price × diluted shares less opening net cash/debt; this is the "
            "source model's implied enterprise cost."
        ),
        share_price_basis="Exact valuation-listing quote, split-adjusted close, in model currency.",
        comparability_group="ENTERPRISE_UFCF",
        cross_method_policy="SAME_METHOD_ONLY",
        limitation=(
            "Not shareholder-distribution IRR. No future debt/cash schedule, interest, financing "
            "or payout policy is modeled, so no enterprise-to-equity bridge is supported."
        ),
    ),
    ReturnMethodology(
        code=UFCF_ENTERPRISE_HMODEL_IRR,
        title="Probability-weighted enterprise UFCF IRR with H-model terminal",
        version=1,
        cash_flow_basis=(
            "Probability-weighted annual unlevered free cash flow through Year 10, plus the "
            "Year 10 UFCF and a Gordon terminal value, with no additional 2.5 terminal-growth "
            "premium in the return stream."
        ),
        perspective="ENTERPRISE",
        entry_value_basis=(
            "Exact listing share price × diluted shares less opening net cash/debt; this is the "
            "source model's implied enterprise cost."
        ),
        share_price_basis="Exact valuation-listing quote, split-adjusted close, in model currency.",
        comparability_group="ENTERPRISE_UFCF_HMODEL",
        cross_method_policy="SAME_METHOD_ONLY",
        limitation=(
            "Not comparable with the legacy enterprise UFCF terminal-premium return method. "
            "Not shareholder-distribution IRR; future financing and payout schedules are absent."
        ),
    ),
    ReturnMethodology(
        code=OWNER_CASH_FLOW_EQUITY_IRR,
        title="Probability-weighted owner cash-flow equity IRR",
        version=1,
        cash_flow_basis=(
            "Probability-weighted owner cash flow per diluted listing share, terminal owner cash "
            "flow, and net cash per share in terminal proceeds."
        ),
        perspective="EQUITY",
        entry_value_basis="Exact valuation-listing share price.",
        share_price_basis="Exact valuation-listing quote, split-adjusted close, in model currency.",
        comparability_group="EQUITY_RETURN",
        cross_method_policy="CONDITIONAL_EQUITY_CROSS_METHOD",
        limitation=(
            "Owner cash flow is an owner-available cash-flow convention, not necessarily an "
            "actual dividend or a forecast of cash distributed to shareholders."
        ),
    ),
    ReturnMethodology(
        code=RESIDUAL_INCOME_EQUITY_IRR,
        title="Probability-weighted residual-income equity IRR",
        version=1,
        cash_flow_basis=(
            "Probability-weighted explicit dividends plus terminal book value and terminal "
            "residual income per share."
        ),
        perspective="EQUITY",
        entry_value_basis="Exact valuation-listing share price.",
        share_price_basis="Exact valuation-listing quote, split-adjusted close, in model currency.",
        comparability_group="EQUITY_RETURN",
        cross_method_policy="CONDITIONAL_EQUITY_CROSS_METHOD",
        limitation=(
            "Uses explicit dividends and book-value/residual-income terminal proceeds; this is a "
            "different shareholder cash-flow basis from owner cash flow."
        ),
    ),
)

DEFINITION_BY_CODE = {item.code: item for item in DEFINITIONS}
DEFINITION_ID_BY_CODE = {
    UFCF_ENTERPRISE_IRR: UUID("7b0f0000-0000-4000-8000-000000000001"),
    UFCF_ENTERPRISE_HMODEL_IRR: UUID("9f170000-0000-4000-8000-000000000001"),
    OWNER_CASH_FLOW_EQUITY_IRR: UUID("7b0f0000-0000-4000-8000-000000000002"),
    RESIDUAL_INCOME_EQUITY_IRR: UUID("7b0f0000-0000-4000-8000-000000000003"),
}


def native_methodology_for_revision(model_type: str, methodology_version: str | None) -> str | None:
    """Return the default method; imports may retain a distinct, evidenced return basis."""
    del methodology_version  # Projection shape alone does not establish terminal-return semantics.
    return NATIVE_METHOD_BY_MODEL_TYPE.get(model_type)


@dataclass(frozen=True)
class ReturnBasis:
    methodology_code: str | None
    methodology_version: int | None
    currency: str | None
    listing_id: str | None = None
    share_price_basis_status: str = "UNAVAILABLE"


def classify_comparability(left: ReturnBasis, right: ReturnBasis) -> str:
    """Classify method/currency comparability without converting rates."""
    if (
        left.methodology_code is None
        or right.methodology_code is None
        or left.methodology_version is None
        or right.methodology_version is None
    ):
        return "UNKNOWN_METHOD"
    left_method = DEFINITION_BY_CODE.get(left.methodology_code)
    right_method = DEFINITION_BY_CODE.get(right.methodology_code)
    if left_method is None or right_method is None:
        return "UNKNOWN_METHOD"
    if left_method.perspective != right_method.perspective:
        return "NOT_COMPARABLE_PERSPECTIVE"
    if (
        left.methodology_version != right.methodology_version
        or left.methodology_version != left_method.version
        or right.methodology_version != right_method.version
    ):
        return "NOT_COMPARABLE_VERSION"

    same_method = left.methodology_code == right.methodology_code
    if not same_method and left_method.perspective != "EQUITY":
        return "NOT_COMPARABLE_METHOD"
    if left.currency is None or right.currency is None:
        return "COMPARABLE_CURRENCY_UNKNOWN"
    cross_currency = left.currency != right.currency
    if same_method:
        return "DIRECT_FX_EXCLUDED" if cross_currency else "DIRECT"
    return "CONDITIONAL_EQUITY_FX_EXCLUDED" if cross_currency else "CONDITIONAL_EQUITY"


def has_comparable_observation_basis(basis: ReturnBasis) -> bool:
    """A point needs an identified listing and retained quote to be comparable."""
    return basis.listing_id is not None and basis.share_price_basis_status == "CAPTURED"


def has_supported_return_methodology(basis: ReturnBasis) -> bool:
    """Require an exact immutable method version understood by this application."""
    definition = DEFINITION_BY_CODE.get(basis.methodology_code or "")
    return definition is not None and basis.methodology_version == definition.version


def methodology_payload() -> dict[str, object]:
    """Return stable definition rows and the supported pairwise comparison policy."""
    rules: list[dict[str, str]] = []
    for left in DEFINITIONS:
        for right in DEFINITIONS:
            status = classify_comparability(
                ReturnBasis(left.code, left.version, "USD"),
                ReturnBasis(right.code, right.version, "USD"),
            )
            rules.append(
                {
                    "left_methodology": left.code,
                    "right_methodology": right.code,
                    "status": status,
                    "rationale": comparability_rationale(status),
                }
            )
    return {
        "definitions": [
            {
                "code": item.code,
                "version": item.version,
                "title": item.title,
                "cash_flow_basis": item.cash_flow_basis,
                "perspective": item.perspective,
                "entry_value_basis": item.entry_value_basis,
                "share_price_basis": item.share_price_basis,
                "comparability_group": item.comparability_group,
                "cross_method_policy": item.cross_method_policy,
                "limitation": item.limitation,
                "effective_from": datetime(2026, 10, 9, tzinfo=UTC),
            }
            for item in DEFINITIONS
        ],
        "rules": rules,
        "currency_policy": (
            "IRR is shown in model-local currency. Cross-currency rates are marked FX_EXCLUDED; "
            "no FX return, inflation adjustment or currency forecast is inferred."
        ),
    }


def comparability_rationale(status: str) -> str:
    return {
        "DIRECT": (
            "Same versioned cash-flow method and currency; listing quote basis is per method."
        ),
        "DIRECT_FX_EXCLUDED": (
            "Same versioned method; local-currency IRRs are shown without forecasting or "
            "converting FX returns."
        ),
        "CONDITIONAL_EQUITY": (
            "Both are equity-perspective returns, but owner cash flow and explicit dividend/book "
            "value cash flows differ economically. Compare with method labels visible."
        ),
        "CONDITIONAL_EQUITY_FX_EXCLUDED": (
            "Equity methods differ and model currencies differ; cash-flow basis and FX effects "
            "remain separate."
        ),
        "COMPARABLE_CURRENCY_UNKNOWN": (
            "Method basis is known; currency is not, so no FX conclusion is available."
        ),
        "NOT_COMPARABLE_PERSPECTIVE": (
            "Enterprise returns and equity returns have different claimholder bases."
        ),
        "NOT_COMPARABLE_VERSION": (
            "Return definition versions differ and no equivalence rule is registered."
        ),
        "NOT_COMPARABLE_METHOD": "No cross-method bridge is supported for these methods.",
        "UNKNOWN_METHOD": (
            "At least one return method is unclassified; comparability is unavailable."
        ),
    }[status]
