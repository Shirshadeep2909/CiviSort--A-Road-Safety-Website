"""Run the CiviSort local server."""

from __future__ import annotations

from civisort import create_app
from civisort.seed import seed_if_empty

app = create_app()


def main() -> None:
    with app.app_context():
        seed_if_empty()
    print("CiviSort is running at http://127.0.0.1:5000/")
    print("Resident/Reviewer is a local demo role switch, not production authentication.")
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
