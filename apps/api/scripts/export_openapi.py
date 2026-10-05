"""Export or verify the deterministic API contract without connecting to PostgreSQL."""

import argparse
import json

from portfolio_api.main import app
from portfolio_api.settings import REPOSITORY_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if the checked-in contract differs"
    )
    arguments = parser.parse_args()
    destination = REPOSITORY_PATH / "packages" / "contracts" / "openapi.json"
    content = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if arguments.check:
        if not destination.exists() or destination.read_text(encoding="utf-8") != content:
            raise SystemExit("OpenAPI contract is stale. Run the contract generation command.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
