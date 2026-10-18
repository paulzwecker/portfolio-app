"""Regression checks against the private workbook's cached ranking values."""

from decimal import Decimal
from pathlib import Path

import pytest

from portfolio_api.legacy_import import MAIN_BOOK, Cell, Workbook
from portfolio_api.research_priority_import import research_priority_rows
from portfolio_api.research_ranking import research_sort_key

pytestmark = pytest.mark.source_data


def _cell_value(row: dict[str, Cell], column: str) -> str | None:
    cell = row.get(column)
    return cell.value if cell is not None else None


def test_legacy_source_inputs_reconcile_representative_cached_research_ranks() -> None:
    workbook_path = Path(__file__).resolve().parents[3] / "reference" / "workbook" / MAIN_BOOK
    workbook = Workbook.read(
        workbook_path, lambda name: name in {"Universe Registry", "Candidate Ranking"}
    )
    inputs = {row["ticker"]: row for row in research_priority_rows(workbook)}
    cached: dict[str, tuple[str | None, str | None]] = {}
    for _row_number, registry_cells in workbook.rows("Universe Registry", 5):
        ticker = _cell_value(registry_cells, "A") or ""
        if ticker:
            cached[ticker.strip().upper()] = (
                _cell_value(registry_cells, "J"),
                _cell_value(registry_cells, "Q"),
            )
    expected = [
        ("NBIS", "LOW", Decimal("0.25"), 1, Decimal("99999.75")),
        ("PGR", "LOW", Decimal("0.28"), 2, Decimal("99999.72")),
        ("TMUS", "LOW", Decimal("0.285"), 3, Decimal("99999.715")),
        ("CBOE", "LOW", Decimal("0.295"), 4, Decimal("99999.705")),
        ("TXN", "LOW", Decimal("0.297"), 5, Decimal("99999.703")),
    ]
    for ticker, tier, priority, rank, sort_key in expected:
        priority_row = inputs[ticker]
        calculated_key, used_default = research_sort_key(
            priority_row["candidate_tier"], priority_row["priority_seed"]
        )
        assert (priority_row["candidate_tier"], priority_row["priority_seed"]) == (
            tier,
            priority,
        )
        assert (calculated_key, used_default) == (sort_key, False)
        assert Decimal(cached[ticker][0] or "NaN") == rank
        assert Decimal(cached[ticker][1] or "NaN") == sort_key

    blank_seed = inputs["CRL"]
    assert blank_seed["priority_seed"] is None
    assert research_sort_key(blank_seed["candidate_tier"], None) == (Decimal("50000"), True)
    # This source row is a known stale cached rank/key rather than a formula input.
    assert cached["FICO"][0] == "1.0"
    assert research_sort_key(inputs["FICO"]["candidate_tier"], inputs["FICO"]["priority_seed"])[
        0
    ] == Decimal("99997.0")
