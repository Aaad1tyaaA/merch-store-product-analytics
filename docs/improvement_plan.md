# Improvement plan and delivery status

I use this list to distinguish completed work from optional extensions. The numbers refer to the original improvement brief.

## Completed

| Original item | Result | Evidence |
|---|---|---|
| 1. Landing and exit pages | First/last observed page titles, product-view coverage and the discovery gap | `07_discovery_evidence.ipynb`, Discovery page, `docs/evidence/landing_pages.csv` |
| 2. Clustered market intervals | User-clustered delta-method intervals and a direct India-minus-US comparison | `scripts/analysis.py`, `docs/evidence/market_comparison.csv` |
| 3. Revenue uncertainty | 1,000 paired whole-user resamples, step intervals and paired differences | `docs/evidence/revenue_bootstrap.csv` and `.json` |
| 4. Proxy and later revenue | Adjusted observational purchase/revenue associations and a conditional projection for the historical non-buyer cohort | `docs/evidence_review.md`; causal and transportability limits remain explicit |
| 13. Definition sensitivity | Alternative transaction keys, requiring session_start and a one-day-earlier window | Evidence page, `docs/evidence/definition_sensitivity.csv` |
| 16. Tracking audit | Retrospective zero/low-volume and order-ID coverage alerts | `docs/evidence/tracking_alerts.csv`; partial recovery still requires daily inspection |

## Delivery completed locally

- Four Power BI pages: Overview, Customers, Discovery and Evidence, with native page navigation.
- Consistent typography, direct chart values, readable axis labels, tested text contrast and descriptive alternative text.
- A native four-page Power BI PDF and four full-page preview images, linked from the README.
- A portable shared template plus an ignored configured working copy. **Open dashboard.cmd** prepares the local report without changing shared paths.
- A one-page decision memo, executed notebooks, exported aggregates, SQL model checks and local dashboard/app tests.

## Partially completed

| Original item | Completed portion | Remaining extension |
|---|---|---|
| 5. Live dashboard and app | Local report refresh, PDF and README previews | Host Streamlit and publish Power BI; verify live links and remote CI after choosing the destination |
| 11. Activation modelling | Calibration, cart-only benchmark, out-of-time AUC, top-decile precision/recall and Brier score | Product-view count thresholds and an activation magic-number analysis |
| 14. CI data coverage | Synthetic SQL/app/report tests run without cloud access | A committed deterministic event sample and its end-to-end rebuild |
| 15. Tested SQL and lineage | Existing model assertions, raw reconciliation and a lineage diagram | A broader declarative contract or dbt migration if the project grows |
| 19. Number traceability | Export/control-total checks and measure comparisons | Exhaustive automated checking of every numerical claim in prose |

## Optional analysis backlog

I would only add these when they answer a new decision; they are not required to use the current dashboard.

- **6-7:** a cross-session user funnel and time-to-first-purchase analysis with censoring handled explicitly.
- **8-10:** search/event paths, peak versus off-peak revenue scenarios, and product/price/cart-abandonment analysis.
- **12:** stronger observational promotion adjustment with overlap checks and clear limits on causal interpretation.
- **17-18:** shared analytical-window configuration and automatic one-page memo rendering in CI.
- **20-21:** a prioritised experiment backlog and a simulated post-test readout template.
- **22:** planner extensions such as revenue scenarios, duration curves, safe CSV import and separately validated sequential inference.
- **23-25:** an India-specific instrumentation plan, a quantified metric tree, interview questions and a short walkthrough video.

## Publication

Local deliverables do not establish a live deployment or a passing remote CI run. I keep publication separate until the repository and hosting destinations are configured. The README links directly to the available PDF, report setup and source rather than claiming a hosted app exists.
