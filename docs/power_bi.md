# Power BI dashboard

`dashboard/merch-store.pbip` is a Power BI project in PBIR (report) and TMDL (semantic model) format. It imports the CSVs in `dashboard/data/`, which `scripts/export_app_data.py` writes from the DuckDB model. `scripts/build_dashboard.py` generates the project files. Every measure is defined there together with a pandas equivalent that `tests/test_dashboard.py` checks against the analysis.

## Open and refresh

1. On Windows, double-click **Open dashboard.cmd** in the repository root. It prepares and opens `dashboard/.local/merch-store.pbip` with the correct absolute data-folder path.
2. In Power BI Desktop, click **Refresh** after the first setup or after updating the CSVs. The repository already includes all fourteen small CSV inputs; BigQuery is not needed to view this report.
3. If I update the analytical data, I first run `python scripts/export_app_data.py`, then refresh the working report.

Command-line alternative: run `python scripts/setup_dashboard.py`, then open the path it prints. The setup uses only Python's standard library. Power BI Desktop must support PBIP/PBIR and TMDL.

The tracked `dashboard/merch-store.pbip` is the **shared template**. Its DataFolder is deliberately blank. I use the configured copy under `.local` for viewing and editing; that folder, its absolute path and its Desktop cache stay out of Git. This separates a portable repository from a report that refreshes on my machine.

Setup preserves an existing local design and updates its data path if the checkout moves. To adopt a newer shared design, I close Desktop and run `python scripts/setup_dashboard.py --replace`. This backs up my local project under `data/dashboard_backups/` before replacing it. Local Desktop design edits must be copied back to the shared template deliberately before sharing, with its DataFolder cleared again.

## Static previews

The [four-page PDF](../output/pdf/merch-store-dashboard.pdf) and [page images](../output/dashboard/) are exported from Power BI Desktop. They are snapshots of the report's default filters, not interactive reports; internal table scroll areas show their visible rows. The complete aggregate tables remain in `dashboard/data/`.

## Control totals

Sessions from 26 Nov 2020 to 25 Jan 2021 (the funnel window). Notebook sources are shown in brackets.

| Visual | Expected value |
|---|---|
| Total sessions card | 248,669 [03, totals] |
| Total orders card | 3,540 [03, totals] |
| Session conversion card | 1.29% (3,196 ÷ 248,669 = 1.2852%) [03, totals] |
| Average order value card | $69.25 [03, totals] |
| Funnel | 248,669 → 50,255 → 13,636 → 6,936 → 4,592 → 3,196 [03, funnel] |
| Revenue at stake, base | View item $5,966; Add to cart $4,443; Begin checkout $2,370; Add payment info $1,821; Order $1,732 [03] |
| Revenue at stake, low / high (View item) | $2,983 / $7,296 [03] |
| Segment table, New vs returning, View item | New 18.5%, Returning 25.3% [03, segments] |
| Activation odds ratio, add to cart | 2.02 (CI 1.56–2.60) [04] |
| Retention, week 1, cohort w/c 30 Nov | 5.0% [04] |
| Channel quality, Paid Search | 4.9% of users, 2.7% of revenue [05] |
| Promotion, raw | 3.57% clicked vs 1.23% did not [05] |
| Promotion, adjusted | 3.75% vs 1.23% [05] |
| Power table, 5% MDE | 29,259 users per arm, 3 weeks [06] |

The session conversion card divides the funnel's order step by its session step. The notebook computes it as the share of sessions with an order. The two must match to the last decimal (`test_measures_match_analysis_totals`).

## Pages

The sidebar links all four pages and highlights the current page. In Desktop editing mode, hold **Ctrl** while clicking a navigation button; in reading mode, use a normal click. Keyboard alternative in Desktop: select a button, then press **Ctrl+Enter**.

1. **Overview — The purchase journey.** Four KPI cards, purchase-stage bars, revenue scenarios and an audience comparison that defaults to new versus returning sessions.
2. **Customers — Customers, intent & the next test.** Activation signals, retention, first-touch channel quality, promotion comparisons and experiment sizing.
3. **Discovery — Inside the discovery gap.** Top-eight observed landing and exit titles, product-view coverage and landing-page order rates. Titles are not verified URLs.
4. **Evidence — Trust the evidence, bound the claim.** Daily tracking coverage, paired user-bootstrap intervals and sensitivity to session/order definitions. Statistical intervals remain separate from business scenarios.

The five additional tables are exported from `docs/evidence/` by `scripts/export_app_data.py`; `scripts/evidence.py` regenerates their analytical sources. Landing and exit tables deliberately contain the top eight titles by session volume, while the full distributions remain in the evidence folder.

## Validation

All report JSON files were validated against Microsoft's published PBIR schemas (`microsoft/json-schemas`, `fabric/item/report/definition`). `tests/test_dashboard.py` checks without network access that:

- every JSON file parses
- TMDL uses tab indentation and one partition per table
- TMDL columns match the CSV headers, with `summarizeBy: none`
- the model contains exactly fourteen tables and has auto date/time disabled
- the shared DataFolder parameter is blank; setup tests verify a separate absolute local path and preserve local edits
- every DAX reference and visual field exists in the model

## Preserving Desktop edits

I refresh CSVs without regenerating report definitions. `python scripts/build_dashboard.py` preserves an existing project; `--regenerate` first copies the report, semantic model and PBIP file to `data/dashboard_backups/<UTC timestamp>/`, then replaces the definitions. The shared project leaves DataFolder blank. `setup_dashboard.py` configures a separate ignored working copy, checks all fourteen input files and preserves existing Desktop edits. Tests require a portable shared template, exactly fourteen CSV-backed tables, auto date/time disabled, no date variations and no implicit column aggregation. Python equivalents check measure totals; they do not execute the DAX engine or prove visual rendering.

## Presentation

The report uses Segoe UI with a 12 pt body/axis/table/data-label floor, 16 pt visual titles, 28 pt page headings and 32 pt KPI values. Pages open at Fit to width, with larger panels and direct chart values. The navy-and-teal palette has tested normal-text contrast. Dense daily trends use selective labels plus an exact dated latest-value summary. Cards show full values, relative lift is formatted as a percentage, and totals are hidden where they would combine unrelated model terms or experiment scenarios. All four pages were visually checked in Power BI Desktop, and the sidebar was used to navigate through Customers, Discovery and Evidence and back to Overview. The local setup supplies DataFolder before refreshing and updates it whenever the repository moves.

The research-backed design checklist and source links are in [Dashboard design standards](dashboard_design.md). In Desktop, collapse the editing panes or maximise the report area when evaluating readability; those panes reduce the available viewing width.
