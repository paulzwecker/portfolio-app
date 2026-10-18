"""Fictional financial model inputs for tests; contains no portfolio source data."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _dcf_years(growth: str, margin: str) -> list[dict[str, str | int]]:
    return [
        {
            "forecast_year": year,
            "revenue_growth": growth,
            "ebit_margin": margin,
            "tax_rate": "0.2",
            "da_to_revenue": "0.03",
            "capex_to_revenue": "0.04",
            "nwc_to_revenue": "0.05",
            "discount_rate": "0.09",
        }
        for year in range(1, 6)
    ]


def dcf_fixture() -> dict[str, Any]:
    scenarios = [
        ("BEAR", "0.25", "0.02", "0.03", "0.05", "0.18"),
        ("BASE", "0.5", "0.025", "0.035", "0.08", "0.2"),
        ("BULL", "0.25", "0.03", "0.04", "0.12", "0.22"),
    ]
    return deepcopy(
        {
            "input": {
                "base_revision_id": None,
                "source_revision_id": "synthetic:dcf:v1",
                "actor": "IMPORT",
                "source": "synthetic test fixture",
                "rationale": "Fictional deterministic regression input.",
                "effective_at": "2026-10-01T00:00:00Z",
                "base": {
                    "base_revenue": "100",
                    "base_ebit_margin": "0.2",
                    "base_tax_rate": "0.2",
                    "base_da_to_revenue": "0.03",
                    "base_capex_to_revenue": "0.04",
                    "base_nwc_to_revenue": "0.05",
                    "net_cash_debt": "10",
                    "diluted_shares": "50",
                },
                "scenarios": [
                    {
                        "scenario": name,
                        "probability": probability,
                        "terminal_growth": terminal_growth,
                        "year10_ufcf_growth": year10_growth,
                        "rationale": "Synthetic scenario input.",
                        "years": _dcf_years(growth, margin),
                    }
                    for (
                        name,
                        probability,
                        terminal_growth,
                        year10_growth,
                        growth,
                        margin,
                    ) in scenarios
                ],
            },
            "market_price": {"price": "20", "currency": "USD"},
            "expected": {
                "bear_fv": "4.8834678230377527926098648333968199876",
                "base_fv": "6.702596927040988980167813384792244469",
                "bull_fv": "9.694556729534570361292706514258035477",
                "weighted_fv": "6.9958046016635752785595495293098361006",
                "weighted_upside": "-0.65020976991682123607202252353450819497",
                "expected_cash_flow_irr": "-0.038014233394250010401832856776594656674",
                "hurdle": "0.0900",
                "expected_excess": "-0.12801423339425001040183285677659465667",
                "bear_y1_ufcf": "13.82000",
                "base_y5_ufcf": "21.495725568000",
                "bull_y10_ufcf": "40.035157807673577661739827200",
            },
        }
    )


def owner_cash_flow_fixture() -> dict[str, Any]:
    scenario_values = [
        ("BEAR", "0.25", "0.12", "0.02", "0.05", "0.18"),
        ("BASE", "0.5", "0.1", "0.025", "0.08", "0.22"),
        ("BULL", "0.25", "0.09", "0.03", "0.12", "0.26"),
    ]
    return deepcopy(
        {
            "model_key": "SYNTHETIC_OWNER_CASH_FLOW",
            "ticker": "SYNTHOCF",
            "input": {
                "base": {
                    "base_revenue": "100",
                    "net_cash": "10",
                    "diluted_shares": "20",
                },
                "scenarios": [
                    {
                        "scenario": name,
                        "probability": probability,
                        "required_return": required_return,
                        "terminal_growth": terminal_growth,
                        "rationale": "Synthetic scenario input.",
                        "years": [
                            {
                                "forecast_year": year,
                                "revenue_growth": growth,
                                "owner_cash_flow_margin": margin,
                            }
                            for year in range(1, 11)
                        ],
                    }
                    for (
                        name,
                        probability,
                        required_return,
                        terminal_growth,
                        growth,
                        margin,
                    ) in scenario_values
                ],
            },
            "market_price": {"price": "25", "currency": "USD"},
            "expected": {
                "bear_fv": "11.734330747789499582722783088684082031",
                "base_fv": "22.971003699942102110152366395306943219",
                "bull_fv": "44.917888282036100988721287517001915311",
                "weighted_fv": "25.648556607427451197937200849074970946",
                "weighted_upside": "0.0259422642970980479174880339629988378",
                "expected_cash_flow_irr": "0.09946294779305865404794423307073617285",
                "hurdle": "0.1025",
                "expected_excess": "-0.00303705220694134595205576692926382715",
            },
        }
    )


def residual_income_fixture() -> dict[str, Any]:
    scenarios = [
        ("BEAR", "0.25", "0.12", "0.11", "0.02", "0.1"),
        ("BASE", "0.5", "0.15", "0.1", "0.02", "0.12"),
        ("BULL", "0.25", "0.18", "0.11", "0.025", "0.14"),
    ]
    return deepcopy(
        {
            "model_key": "SYNTHETIC_RESIDUAL_INCOME",
            "ticker": "SYNTHRI",
            "input": {
                "base": {"current_book_value_per_share": "20", "payout_ratio": "0.5"},
                "scenarios": [
                    {
                        "scenario": name,
                        "probability": probability,
                        "starting_roe": starting_roe,
                        "cost_of_equity": cost_of_equity,
                        "terminal_growth": terminal_growth,
                        "mature_roe": mature_roe,
                        "rationale": "Synthetic scenario input.",
                    }
                    for (
                        name,
                        probability,
                        starting_roe,
                        cost_of_equity,
                        terminal_growth,
                        mature_roe,
                    ) in scenarios
                ],
            },
            "market_price": {"price": "24", "currency": "INR"},
            "expected": {
                "bear_fv": "19.330223480871874678297249819058288665",
                "base_fv": "30.707845992956655293014310862111795368",
                "bull_fv": "35.422682434348607689267433011698416076",
                "weighted_fv": "29.042149475283448238398326138745073869",
                "weighted_upside": "0.2100895614701436765999302557810447445",
                "expected_cash_flow_irr": "0.13154870700697890728942112627671606114",
                "hurdle": "0.1050",
                "expected_excess": "0.02654870700697890728942112627671606114",
            },
        }
    )
