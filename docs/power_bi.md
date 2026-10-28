# Power BI dashboard

`dashboard/merch-store.pbip` is a Power BI project in PBIR (report) and TMDL (semantic model) format. It imports the CSVs in `dashboard/data/`, which `scripts/export_app_data.py` writes from the DuckDB model. `scripts/build_dashboard.py` generates the project files. Every measure is defined there together with a pandas equivalent that `tests/test_dashboard.py` checks against the analysis.

## Refresh

1. Run `python scripts/export_app_data.py` to rewrite `dashboard/data/*.csv`. This is not needed if the CSVs in the repository are current.
2. Open `dashboard/merch-store.pbip` in Power BI Desktop. PBIP and TMDL must be enabled under *Options → Preview features*.
3. Go to *Transform data → Edit parameters* and set **DataFolder** to the full path of `dashboard\data` on your machine, with no trailing slash.
4. Click *Refresh*, then check every number against the table below.
5. Export: *File → Export → Export to PDF*. Save it as `dashboard/merch-store-dashboard.pdf`.

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

1. **Where we lose buyers:** cards, the funnel, revenue at stake by step (low, base, high), and segment step conversion with a dimension slicer.
2. **Who buys and what to test:** activation odds ratios, a weekly retention matrix with a background gradient, first-touch channel quality, the promotion raw vs adjusted gap, and the test's power table.

## Validation

All report JSON files were validated against Microsoft's published PBIR schemas (`microsoft/json-schemas`, `fabric/item/report/definition`). `tests/test_dashboard.py` checks without network access that:

- every JSON file parses
- TMDL uses tab indentation and one partition per table
- TMDL columns match the CSV headers
- every DAX reference and visual field exists in the model
