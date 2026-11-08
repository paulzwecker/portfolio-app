"""Collection must route database workflows to CI's isolated PostgreSQL job."""

from pathlib import Path

import pytest

pytest_plugins = ("pytester",)


def _sandbox(pytester: pytest.Pytester) -> None:
    pytester.makeini(
        """[pytest]
addopts = --strict-markers
markers =
    integration: isolated PostgreSQL required
    source_data: operator-provided source files required
"""
    )
    source = Path(__file__).with_name("conftest.py")
    pytester.makeconftest(
        "from runpy import run_path\n"
        f"hooks = run_path({str(source)!r})\n"
        "pytest_collection_modifyitems = hooks['pytest_collection_modifyitems']\n"
    )


@pytest.mark.parametrize(
    "selector", ["not integration and not source_data", "integration and not source_data"]
)
def test_unmarked_database_test_fails_before_marker_deselection(
    pytester: pytest.Pytester, selector: str
) -> None:
    _sandbox(pytester)
    pytester.makepyfile(
        test_unclassified="""
import pytest

@pytest.fixture
def postgres_engine():
    raise AssertionError("Database fixture must never execute during collection")

@pytest.fixture
def statement_store(postgres_engine):
    return postgres_engine

@pytest.mark.parametrize(
    "record", ["synthetic-private-parameter-a", "synthetic-private-parameter-b"]
)
def test_statement(statement_store, record):
    pass
"""
    )
    result = pytester.runpytest_subprocess("-q", "-m", selector)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    output = result.stdout.str() + result.stderr.str()
    assert "PostgreSQL tests require @pytest.mark.integration" in output
    assert output.count("test_unclassified.py::test_statement") == 1
    assert "synthetic-private-parameter" not in output
    assert "Database fixture must never execute" not in output


@pytest.mark.parametrize(
    ("selector", "included", "excluded"),
    [
        (
            "not integration and not source_data",
            "::test_unit",
            ["::test_query", "::test_operator_source"],
        ),
        (
            "integration and not source_data",
            "::test_query",
            ["::test_unit", "::test_operator_source"],
        ),
        ("source_data", "::test_operator_source", ["::test_unit", "::test_query"]),
    ],
)
def test_inherited_markers_and_source_opt_in_preserve_job_boundaries(
    pytester: pytest.Pytester, selector: str, included: str, excluded: list[str]
) -> None:
    _sandbox(pytester)
    pytester.makepyfile(
        test_classified="""
import pytest

@pytest.fixture
def postgres_engine():
    raise AssertionError("Database fixture must never execute during collection")

@pytest.fixture
def statement_store(postgres_engine):
    return postgres_engine

@pytest.mark.integration
class TestDatabase:
    def test_query(self, statement_store):
        pass

@pytest.mark.source_data
def test_operator_source(statement_store):
    pass

def test_unit():
    pass
"""
    )
    result = pytester.runpytest_subprocess("--collect-only", "-q", "-m", selector)
    assert result.ret == pytest.ExitCode.OK
    output = result.stdout.str() + result.stderr.str()
    assert included in output
    for name in excluded:
        assert name not in output
    assert "Database fixture must never execute" not in output


def test_dynamic_database_fixture_request_fails_before_missing_database_skip(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sandbox(pytester)
    source = Path(__file__).with_name("conftest.py")
    pytester.makeconftest(
        "from runpy import run_path\n"
        f"hooks = run_path({str(source)!r})\n"
        "pytest_collection_modifyitems = hooks['pytest_collection_modifyitems']\n"
        "postgres_engine = hooks['postgres_engine']\n"
    )
    monkeypatch.setenv("TEST_DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_URL", "")
    pytester.makepyfile(
        test_dynamic="""
def test_statement(request):
    request.getfixturevalue("postgres_engine")
"""
    )
    result = pytester.runpytest_subprocess("-q", "-m", "not integration and not source_data")
    result.assert_outcomes(failed=1, skipped=0)
    assert "PostgreSQL tests require @pytest.mark.integration" in result.stdout.str()
    assert "Set TEST_DATABASE_URL" not in result.stdout.str()
