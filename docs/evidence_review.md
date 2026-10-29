# Discovery evidence and verification

I reproduced this analysis locally with `python scripts/evidence.py`. The script reads the database without changing it and writes the CSV evidence linked below. Notebook 07 displays the same results and charts.

## Landing and exit pages

I use the first and last recorded `page_view` title in each funnel-window session, ordered by UTC timestamp and event ID. These are observed page titles, not URLs or confirmed acquisition landing pages. Titles can be shared across URLs; equal timestamps have no verified order. Sessions without a page view remain visible.

| landing_page | sessions | product_view_rate | order_session_rate | share_of_sessions |
|---|---|---|---|---|
| Home | 68567 | 0.2421 | 0.0243 | 0.2757 |
| Google Online Store | 41079 | 0.1233 | 0.0057 | 0.1652 |
| Apparel / Google Merchandise Store | 33585 | 0.0751 | 0.0024 | 0.1351 |
| Google Dino Game Tee | 16797 | 0.0749 | 0.0001 | 0.0675 |
| [No page_view] | 16494 | 0.0132 | 0.0 | 0.0663 |
| YouTube / Shop by Brand / Google Merchandise Store | 16452 | 0.1946 | 0.0021 | 0.0662 |
| Men's T-Shirts / Apparel / Google Merchandise Store | 4636 | 0.3574 | 0.0067 | 0.0186 |
| Page Unavailable | 3757 | 0.0538 | 0.0 | 0.0151 |
| Drinkware / Lifestyle / Google Merchandise Store | 3099 | 0.1078 | 0.01 | 0.0125 |
| Shopping Cart | 2642 | 0.3611 | 0.1007 | 0.0106 |

Among sessions without a product-view event, the most common last observed pages are:

| exit_page | sessions | share_of_nonview_sessions |
|---|---|---|
| Home | 44406 | 0.2238 |
| Apparel / Google Merchandise Store | 30630 | 0.1544 |
| Google Online Store | 28687 | 0.1446 |
| [No page_view] | 16276 | 0.082 |
| Google Dino Game Tee | 15335 | 0.0773 |
| YouTube / Shop by Brand / Google Merchandise Store | 11837 | 0.0597 |
| Store search results | 3783 | 0.0191 |
| Drinkware / Lifestyle / Google Merchandise Store | 3470 | 0.0175 |

I found product-titled landing pages without `view_item`, and sessions without any `page_view`. I therefore validate event coverage before interpreting every non-viewer as a discovery failure. The best-seller grid is a testable hypothesis; this analysis does not establish why people leave. I would validate homepage and category-page tracking first, then test a grid on eligible landing pages.

## Clustered market comparisons

I now calculate delta-method standard errors clustered by cookie ID, keeping every session from a cookie together. I test the India-minus-US difference against zero rather than comparing overlap between two separate confidence intervals. The data show no clear difference at any step; this does not establish equivalence. The full differences and intervals are in [market_comparison.csv](evidence/market_comparison.csv).

## Revenue scenario uncertainty

I resample 193,296 whole users with replacement, using 1,000 paired bootstrap draws and seed 42. Every user's sessions stay together; the observed 61-day calendar stays fixed.

| step | usd_base | ci_low | ci_high |
|---|---|---|---|
| View item | 5965.69 | 5640.62 | 6295.13 |
| Add to cart | 4443.35 | 4191.68 | 4693.01 |
| Begin checkout | 2370.26 | 2242.66 | 2498.34 |
| Add payment info | 1821.06 | 1722.58 | 1916.68 |
| Order | 1732.26 | 1638.06 | 1822.71 |

The product-view scenario is $5,966 per 30 days, with a sampling interval of $5,641–$6,295. Its paired difference from add to cart has a 95% interval of $1,401–$1,649. Product view exceeds cart in 100.0% of bootstrap draws. This is a resampling frequency, not a posterior probability.

These intervals describe sampling uncertainty **conditional on the +1-point model**. They do not quantify whether an intervention can produce that gain or whether marginal viewers behave like existing viewers. Low/base/high sensitivity cases remain separate from these sampling intervals. Under the model, dollar rankings are inversely proportional to step conversion by construction.

## Product views and later purchases

I compare new users first seen 26 November–26 December who did not buy in their first session. Outcomes are a purchase indicator and revenue within 30 days of the first session. I adjust for first-session device, market, first-touch channel and cohort week with linear models and HC3 robust standard errors. I avoid engagement/cart/checkout controls because these can follow product viewing.

The adjusted purchase-rate difference is 2.44% (95% interval 2.20%–2.68%). The adjusted revenue difference is $2.16 per person ($1.83–$2.49).

Applying a 5% relative view-rate lift to this **historical non-buyer cohort only** gives 946.8 extra viewers. If the adjusted association transferred unchanged to those marginal viewers, that corresponds to 23.1 additional purchasing users (20.9–25.4) and $2,046 revenue ($1,731–$2,361). This is neither a monthly estimate nor an estimate for the full experiment population. The intervals are conditional on fixed exposure lift and model specification; they omit unmeasured confounding, exposure-model uncertainty and transportability. Only a randomized holdout can estimate causal revenue impact.

## Tracking audit

I flag zero-volume days and counts below 20% of the median of the six neighbouring days. I also flag valid-purchase coverage below 80% of its full-period median, which catches sustained low-but-nonzero ID coverage after 25 January. There are 48 metric-day alerts; several metrics can flag the same date. The audit uses future days and a full-period reference: it is retrospective, not live monitoring. The count rule misses partial recovery on 16–19 and 25 November, so the 26 November funnel start also relies on daily event inspection rather than this audit alone. Alerts require inspection and never remove data automatically. Full results: [tracking_alerts.csv](evidence/tracking_alerts.csv).

## Activation diagnostics and sensitivity

On the out-of-time test set, the full activation model has AUC 0.869, versus 0.655 for the cart-only rule. Top-decile precision is 3.99%, recall 62.8%, and Brier score 0.00610. [Calibration by decile](evidence/activation_calibration.csv) makes prediction quality inspectable; AUC alone does not establish calibration.

I also rerun control totals under alternative order keys, requiring `session_start`, and starting the funnel one day earlier: [definition_sensitivity.csv](evidence/definition_sensitivity.csv). These are separate scenarios, not new default definitions.
