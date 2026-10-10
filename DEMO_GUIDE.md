# CiviSort five-minute demo

Start the app with `run.bat` and open http://127.0.0.1:5000/. Everything shown is synthetic demonstration data. Scores are planning assumptions, not accident predictions.

## 1. Orientation (30 s)
The left list ranks reports by priority; the map and the list show the same reports, and clicking a pin or a list card opens the same detail panel. Each report shows an **Evidence** label (unverified / verified / disputed) separate from its **Repair** label. Try the Category / Evidence / Repair filters. Note the urgent but **unverified** report near the top, flagged "Needs inspection": it is shown, not hidden.

## 2. Resident reporting (60 s)
Keep the role on **Resident**. Click the map to choose a spot, then **Report a hazard**: pick a category, write a description, optionally attach a photo (JPEG/PNG/WebP/GIF up to 5 MB; it is re-encoded and stripped of metadata) and submit. The report appears as *unverified* and opens in the detail panel. A report placed within 50 m of a same-category report is flagged as a possible duplicate. Invalid input (for example an empty description) shows a clear error.

## 3. Reviewer verification (45 s)
Switch to **Reviewer** and open your new report. Fill in severity, exposure, vulnerable-user context and a cost in INR (explanations are next to the fields), then **Verify evidence**. Evidence becomes *verified* and the repair status *verified* - two separate labels.

## 4. ContextShift and Priority Breakdown (60 s)
Open a pothole and watch the **Priority breakdown** bars (Severity, Exposure, Vulnerability, Conditions, Age) while toggling **Rain**. Conditions jumps by 15 points and the ranking changes. **Night** affects streetlights, **School Hours** affects school-access hazards, and several matching scenarios never stack. All numbers come from the backend.

## 5. BudgetMix and saved plans (60 s)
Look at the BudgetMix panel (budget defaults to INR 70,000). Move the slider or type another budget: the optimiser selects the bundle with the most priority points, shows actual spend and remaining budget, compares with a priority-first baseline, and lists why each other report was excluded. Costs are rounded **up** and the budget **down** to INR 1,000 units. As Reviewer, click **Save this plan snapshot**: the chosen reports become *Planned* and a snapshot (budget, scenarios, per-report breakdowns) is stored under "Saved snapshots". Changing the live settings afterwards does not alter it.

## 6. Repair Receipt (45 s)
Open a **Planned** report as Resident, add a completion note (or an after-photo) and **Claim repair**. Switch to Reviewer and **Confirm closure**: the report leaves the active list (choose Repair filter "Closed" to see it). Enter a reason and press **Reopen** to return it to Planned. The History list shows every step with timestamps. The seeded data also includes a repair already claimed and awaiting confirmation, and a closed one with history.

## Optional extras
- **Duplicates:** a Reviewer can confirm a merge on a primary report; the duplicate is kept as linked history and excluded from ranking and planning.
- **Map fallback:** if the online map tiles cannot load (for example no internet), a labelled schematic replaces them and pins stay selectable.
