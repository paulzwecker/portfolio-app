"""Reviewed, explicit mappings for direct-Sheets UFCF DCF package capture.

Each entry is tied to an already parity-proven model tab. These declarations
describe cell layout only; they contain no company financial values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from portfolio_api.model_input_migration import (
    PORTFOLIO_DCF_EXPLICIT_TAIL_MAPPING_VERSION,
    PORTFOLIO_DCF_MAPPING_VERSION,
)

TEMPLATE_CONTRACT_VERSION = "google-sheets-dcf-template-v1"

# Common native-field mappings are explicit and version-controlled. Per-tab
# configurations below select the exact scenario growth and tail cells.
BASE_INPUT_CELLS = (
    ("base.base_revenue", "B17"),
    ("base.base_ebit_margin", "B18"),
    ("base.base_tax_rate", "B19"),
    ("base.base_da_to_revenue", "B20"),
    ("base.base_capex_to_revenue", "B21"),
    ("base.base_nwc_to_revenue", "B22"),
    ("base.net_cash_debt", "B23"),
    ("base.diluted_shares", "B24"),
)
SCENARIO_PROBABILITY_CELLS = (("BEAR", "AO4"), ("BASE", "AO5"), ("BULL", "AO6"))
SCENARIO_TERMINAL_GROWTH_CELLS = (
    ("BEAR", "B205"),
    ("BASE", "C205"),
    ("BULL", "D205"),
)
SCENARIO_COLUMNS = (
    ("BEAR", ("E", "F", "G", "H", "I")),
    ("BASE", ("J", "K", "L", "M", "N")),
    ("BULL", ("O", "P", "Q", "R", "S")),
)
YEAR_ASSUMPTION_ROWS = (
    ("revenue_growth", 16),
    ("ebit_margin", 17),
    ("da_to_revenue", 18),
    ("capex_to_revenue", 19),
    ("nwc_to_revenue", 20),
    ("tax_rate", 21),
    ("discount_rate", 22),
)
PUBLISHED_OUTPUT_CELLS = (
    ("parity_reference_price", "B4"),
    ("bear_fair_value_per_share", "L202"),
    ("base_fair_value_per_share", "M202"),
    ("bull_fair_value_per_share", "N202"),
    ("bear_probability", "AO4"),
    ("base_probability", "AO5"),
    ("bull_probability", "AO6"),
    ("weighted_fair_value_per_share", "AO7"),
    ("weighted_upside", "AO8"),
    ("expected_cash_flow_irr", "AA212"),
    ("hurdle", "AB212"),
    ("expected_excess", "AC212"),
)
PROJECTION_ROWS = (("BEAR", 40), ("BASE", 60), ("BULL", 80))
PROJECTION_TAIL_COLUMNS = (("BEAR", "G"), ("BASE", "H"), ("BULL", "I"))
PROJECTION_VALUE_COLUMNS = ("C", "D", "E", "F", "G")
PROJECTION_TAIL_ROWS = (202, 203, 204, 205, 206)
RETURN_STREAM_COLUMNS = ("P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z")

_COMMON_DCF_OUTPUT_RANGES = (
    "L202:N202",
    "AO4:AO8",
    "C40:G40",
    "C60:G60",
    "C80:G80",
    "G202:G206",
    "H202:H206",
    "I202:I206",
    "P212:Z212",
    "AA212:AC212",
)


@dataclass(frozen=True)
class DcfModelTemplate:
    model_key: str
    template_id: str
    template_version: str
    mapping_version: str
    mapper: Literal["GOOGL", "PORTFOLIO_DCF"]
    company_name: str
    ticker: str
    venue: str
    currency: str
    required_formula_cells: tuple[str, ...]
    ranges: tuple[str, ...]
    base_input_cells: tuple[tuple[str, str], ...]
    probability_cells: tuple[tuple[str, str], ...]
    terminal_growth_cells: tuple[tuple[str, str], ...]
    scenario_columns: tuple[tuple[str, tuple[str, ...]], ...]
    year_assumption_rows: tuple[tuple[str, int], ...]
    year10_growth_cells: tuple[tuple[str, tuple[str, ...]], ...]
    tail_growth_ranges: tuple[tuple[str, str], ...]
    output_cells: tuple[tuple[str, str], ...]
    scenario_rationale: str
    projection_rows: tuple[tuple[str, int], ...]
    projection_value_columns: tuple[str, ...]
    projection_tail_columns: tuple[tuple[str, str], ...]
    projection_tail_rows: tuple[int, ...]
    return_stream_columns: tuple[str, ...]
    min_row_count: int = 212
    min_column_count: int = 42


DCF_MODEL_TEMPLATES: dict[str, DcfModelTemplate] = {
    "P-GOOGL": DcfModelTemplate(
        model_key="P-GOOGL",
        template_id="p-googl-ufcf-growth-grid",
        template_version=TEMPLATE_CONTRACT_VERSION,
        mapping_version="google-sheets-package-v2-p-googl-growth-grid-v1",
        mapper="GOOGL",
        company_name="Alphabet",
        ticker="GOOGL",
        venue="NASDAQ",
        currency="USD",
        required_formula_cells=(
            "E16",
            "L202",
            "M202",
            "N202",
            "AO7",
            "AO8",
            "AA212",
            "AB212",
            "AC212",
        ),
        base_input_cells=BASE_INPUT_CELLS,
        probability_cells=SCENARIO_PROBABILITY_CELLS,
        terminal_growth_cells=SCENARIO_TERMINAL_GROWTH_CELLS,
        scenario_columns=SCENARIO_COLUMNS,
        year_assumption_rows=YEAR_ASSUMPTION_ROWS,
        year10_growth_cells=(
            ("BEAR", ("E24", "F24", "G24", "H24", "I24")),
            ("BASE", ("J24", "K24", "L24", "M24", "N24")),
            ("BULL", ("O24", "P24", "Q24", "R24", "S24")),
        ),
        tail_growth_ranges=(),
        output_cells=PUBLISHED_OUTPUT_CELLS,
        scenario_rationale="source labels and mapped assumption range",
        projection_rows=PROJECTION_ROWS,
        projection_value_columns=PROJECTION_VALUE_COLUMNS,
        projection_tail_columns=PROJECTION_TAIL_COLUMNS,
        projection_tail_rows=PROJECTION_TAIL_ROWS,
        return_stream_columns=RETURN_STREAM_COLUMNS,
        ranges=(
            "B4",
            "B12",
            "B15",
            "B17:B24",
            "E16:S22",
            "E24:S24",
            "B205:D205",
            *_COMMON_DCF_OUTPUT_RANGES,
        ),
    ),
    "P-CPRT": DcfModelTemplate(
        model_key="P-CPRT",
        template_id="portfolio-ufcf-explicit-terminal-growth",
        template_version=TEMPLATE_CONTRACT_VERSION,
        mapping_version=PORTFOLIO_DCF_MAPPING_VERSION,
        mapper="PORTFOLIO_DCF",
        company_name="Copart",
        ticker="CPRT",
        venue="NASDAQ",
        currency="USD",
        required_formula_cells=(
            "B210",
            "L202",
            "M202",
            "N202",
            "AO7",
            "AO8",
            "AA212",
            "AB212",
            "AC212",
        ),
        base_input_cells=BASE_INPUT_CELLS,
        probability_cells=SCENARIO_PROBABILITY_CELLS,
        terminal_growth_cells=SCENARIO_TERMINAL_GROWTH_CELLS,
        scenario_columns=SCENARIO_COLUMNS,
        year_assumption_rows=YEAR_ASSUMPTION_ROWS,
        year10_growth_cells=(
            ("BEAR", ("B210",)),
            ("BASE", ("C210",)),
            ("BULL", ("D210",)),
        ),
        tail_growth_ranges=(),
        output_cells=PUBLISHED_OUTPUT_CELLS,
        scenario_rationale="source scenario labels and mapped range",
        projection_rows=PROJECTION_ROWS,
        projection_value_columns=PROJECTION_VALUE_COLUMNS,
        projection_tail_columns=PROJECTION_TAIL_COLUMNS,
        projection_tail_rows=PROJECTION_TAIL_ROWS,
        return_stream_columns=RETURN_STREAM_COLUMNS,
        ranges=(
            "B4",
            "B12",
            "B15",
            "B17:B24",
            "E16:S22",
            "B205:D205",
            "B210:D210",
            *_COMMON_DCF_OUTPUT_RANGES,
        ),
    ),
    "P-AMZN": DcfModelTemplate(
        model_key="P-AMZN",
        template_id="portfolio-ufcf-explicit-year-six-to-ten-tail",
        template_version=TEMPLATE_CONTRACT_VERSION,
        mapping_version=PORTFOLIO_DCF_EXPLICIT_TAIL_MAPPING_VERSION,
        mapper="PORTFOLIO_DCF",
        company_name="Amazon",
        ticker="AMZN",
        venue="NASDAQ",
        currency="USD",
        required_formula_cells=("L202", "M202", "N202", "AO7", "AO8", "AA212", "AB212", "AC212"),
        base_input_cells=BASE_INPUT_CELLS,
        probability_cells=SCENARIO_PROBABILITY_CELLS,
        terminal_growth_cells=SCENARIO_TERMINAL_GROWTH_CELLS,
        scenario_columns=SCENARIO_COLUMNS,
        year_assumption_rows=YEAR_ASSUMPTION_ROWS,
        year10_growth_cells=(
            ("BEAR", ("B210",)),
            ("BASE", ("C210",)),
            ("BULL", ("D210",)),
        ),
        tail_growth_ranges=(
            ("BEAR", "B206:B210"),
            ("BASE", "C206:C210"),
            ("BULL", "D206:D210"),
        ),
        output_cells=PUBLISHED_OUTPUT_CELLS,
        scenario_rationale="source scenario labels and mapped range",
        projection_rows=PROJECTION_ROWS,
        projection_value_columns=PROJECTION_VALUE_COLUMNS,
        projection_tail_columns=PROJECTION_TAIL_COLUMNS,
        projection_tail_rows=PROJECTION_TAIL_ROWS,
        return_stream_columns=RETURN_STREAM_COLUMNS,
        ranges=(
            "B4",
            "B12",
            "B15",
            "B17:B24",
            "E16:S22",
            "B205:D205",
            "B206:D210",
            *_COMMON_DCF_OUTPUT_RANGES,
        ),
    ),
}


def get_dcf_model_template(model_key: str) -> DcfModelTemplate:
    """Return only an explicitly reviewed template; never infer a layout."""
    try:
        return DCF_MODEL_TEMPLATES[model_key]
    except KeyError:
        raise ValueError(
            "No reviewed direct-Sheets DCF template supports that model key."
        ) from None
