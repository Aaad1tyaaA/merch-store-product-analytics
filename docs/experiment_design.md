# Experiment design: product discovery for new visitors

Every number here comes from `06_experiment_design.ipynb` and `03_funnel_revenue_at_stake.ipynb` (funnel window: 26 Nov 2020 – 25 Jan 2021).

## Why this test

Session → product view is the funnel step with the most revenue at stake. Only 20.2% of sessions view a product, and one extra point there is worth about $5,966 per 30 days (range $2,983–$7,296). That is more than any later step.

Within this step, new sessions are the weakest large segment: 18.5% view a product, against 25.3% of returning sessions, and new sessions are 74.6% of all sessions. Mobile checkout, the usual suspect, converts as well as desktop in this data, so it is not the first test.

## Hypothesis

If new visitors see a grid of best-selling products in the first screen of the page they land on, more of them will view a product in their first session, because 80% of sessions currently end without reaching a product page.

- **H0:** the first-session product-view rate is the same in both arms.
- **H1:** it differs (two-sided).

## Population

New users only: a user's first observed session, `ga_session_number = 1`. All devices and markets are included. Internal and bot traffic is excluded with the same filters the production property uses.

## Randomisation unit

`user_pseudo_id`, assigned 50/50 at the first page view by a hash of the id, so a user who returns sees the same arm. This is a browser, not a person: one person on two devices can land in both arms. That contamination dilutes the effect towards zero, so it makes the test conservative.

## Primary metric

Share of new users who view a product (`view_item`) in their first session.

Baseline: 17.95%, the average of five non-holiday weeks. It ranged from 13.8% to 22.6% week to week, so only a concurrent control is a valid comparison; a before/after read is not.

## Guardrails

Each is tested for harm (one-sided, α = 0.05). Any significant harm blocks a launch.

| Guardrail | Baseline | Why |
|---|---|---|
| First-session order rate | 0.60% | The grid must not pull users away from buying |
| AOV | $69.25 | Best sellers could shift buyers to cheaper items |
| Revenue per session | $0.99 | Combines the two above |
| Page load time on landing pages | measured at launch | A heavier first screen can slow mobile pages |

The order rate cannot be powered on this traffic: detecting a 10% change would take about 24 weeks. It is watched for large harm only, and the test does not claim a revenue effect.

## Sample size and duration

Two-sided α = 0.05, power 0.8, 50/50 split, 23,349 new users per week.

| Relative MDE | Absolute (points) | Users per arm | Weeks |
|---:|---:|---:|---:|
| 2% | 0.36 | 180,790 | 16 |
| 3% | 0.54 | 80,660 | 7 |
| **5%** | **0.90** | **29,259** | **3** |
| 7.5% | 1.35 | 13,126 | 2 |
| 10% | 1.80 | 7,451 | 2 |

**Plan:** 5% relative MDE, 29,259 users per arm, **three full weeks**, Monday to Sunday. That covers weekday patterns, beats the two-week minimum, and stays clear of Black Friday to Cyber Monday and 21 December to 3 January. In the 2020–21 calendar the slot would have been 11–31 January.

**CUPED:** new users have no pre-period, so CUPED gives them no variance reduction, and the sample size above assumes none. If the test is later widened to returning users, using whether they viewed a product in the previous four weeks as the covariate cuts variance by 14.9% (correlation 0.39, 2,267 returning users). That is about 15% fewer users needed for that population.

## Sample ratio mismatch

`srm_check()` in `app/stats.py` runs a chi-square test on users per arm every day from day one. If p < 0.001, stop reading results and fix assignment first. Typical causes are a redirect, a caching layer serving one arm, or bot filtering applied to one arm.

For scale: at 29,259 control users, a treatment arm 3% short (28,381) gives p = 0.0003 and fails. A 150-user difference passes (p = 0.54).

## Decision rule (fixed before launch)

After three full weeks, with SRM passed:

1. **Ship** if the primary metric improves with p < 0.05 and no guardrail shows significant harm.
2. **Iterate** if the primary metric improves but a guardrail is harmed: change the design and test again.
3. **Do not ship** if the primary metric shows no significant change. Report the 95% interval, which bounds the effect the grid could have.

## No peeking

Results are read once, at the end of week three. Daily dashboards show the SRM check and guardrails only. The primary metric stays hidden until the end, because stopping the first time p < 0.05 inflates false positives well above 5%. An early stop happens only for SRM or a severe guardrail breach, never for a good-looking primary result.

## Risks

- **Novelty:** a new first screen can draw clicks that fade. Compare week 1 with week 3. If the lift halves, report the week-3 effect.
- **Proxy metric:** a product view is a leading indicator, not revenue. The activation analysis shows engaged first sessions predict later purchase, but more product views will not necessarily produce more orders. A follow-up test or a long-running holdout settles revenue.
- **Cookie identity:** a returning person with cleared cookies is enrolled again as a new user. That is accepted because it hits both arms equally.
- **Data quality:** the sample used to plan this test has tracking gaps (`add_to_cart` missing for most of November 2020, order ids missing after 25 January 2021). Check event tracking for both arms in the first two days before trusting any metric.
