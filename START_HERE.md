# CiviSort - START HERE (judges)

CiviSort is a **local prototype**: a Flask + SQLite web app that helps residents report road hazards and helps reviewers choose which **verified** repairs to fund within a budget. It runs entirely on your own computer.

Please note:

- **Demo roles are not production authentication.** The Resident / Reviewer switch only demonstrates permissions (the server does enforce them, but anyone can switch).
- **Scores are planning assumptions**, not measured accident risk. CiviSort does not predict accidents.
- **All sample reports are synthetic demonstration data** for a fictional "Ashoka Ward".
- **Map tiles need internet** (OpenStreetMap). If they cannot load, a clearly labelled **local schematic map** takes over and everything still works.

## Prerequisites

- Windows 10 or 11
- Python 3.11 or newer from https://www.python.org/downloads/ (tick "Add python.exe to PATH"; the `py` launcher also works). Submission tests were run with Python 3.12.14 on Linux; Windows launchers were inspected but not executed.
- Internet connection for the first start (to install Flask and Pillow with pip) and, optionally, for map tiles
- Any modern browser

## Start (Windows)

1. Download the repository ZIP and extract it, or clone https://github.com/Shirshadeep2909/CiviSort--A-Road-Safety-Website. Open the repository root containing **app.py** and **run.bat**.
2. Double-click **run.bat** (or run `run.bat` in Command Prompt from that folder).
   - It creates `.venv`, installs the pinned packages from `requirements.txt`, then starts the server.
3. Open **http://127.0.0.1:5000/** in your browser.
4. Stop with Ctrl+C in the console window.

No PowerShell activation or Node.js is needed. First start creates `data\civisort.sqlite3` and **about 20 synthetic reports** automatically. Later starts keep all data; nothing is reset unless you choose to.

Run the tests (76 tests passed during submission preparation, using temporary databases): double-click **run_tests.bat**.

## Demo roles

- **Resident** (default): report a hazard (click the map to choose the spot), optionally add a photo, and claim a completed repair on a planned report.
- **Reviewer**: verify/dispute evidence, set severity, exposure, vulnerable-user context and cost, confirm duplicate merges, save plans, confirm repair closure, reopen a repair with a reason.

Switch with the "Demo role" box at the top of the page. A guided five-minute tour is in **DEMO_GUIDE.md**.

## Sample data and reset

Sample data is created by `civisort\seed.py` only when the database is empty. **Stop the server and back up any data you want to keep first.** To wipe everything and recreate the demo on purpose, run **reset_demo.bat** and type `RESET` when asked (it deletes reports, plans and photos in `data\`).

## Troubleshooting

| Problem | Fix |
|---|---|
| "python is not recognized" | Install Python 3.11+ and tick "Add python.exe to PATH", or install the `py` launcher; then rerun `run.bat`. |
| pip install fails | Check your internet connection / proxy and rerun `run.bat`. |
| Port 5000 already in use | Close the other program using port 5000 (or an old CiviSort window) and rerun. |
| Map is grey or shows "Using the labelled local schematic" | OpenStreetMap tiles are unreachable. This is expected offline; the schematic works the same (select pins, click it to place a report). |
| Want a clean demo | Run `reset_demo.bat` (asks for confirmation). |
| Antivirus/SmartScreen warns about run.bat | It only creates a virtual environment, installs the packages listed in `requirements.txt` and starts the local server. |

See README.md for scoring, BudgetMix rounding and known limitations.
