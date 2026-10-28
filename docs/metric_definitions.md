# Metric definitions

Written before any analysis and applied unchanged in every notebook, the dashboard and the app. All SQL lives in `sql/02_model.sql` and `sql/03_metrics.sql`.

## Units

| Unit | Definition | Notes |
|---|---|---|
| User | One `user_pseudo_id` | A browser or device cookie, not a person. One person on phone and laptop is two users. |
| Session | `user_pseudo_id` + `ga_session_id` | `ga_session_id` is a session start time in seconds and repeats across users, so it is never used alone. |
| New session | `ga_session_number = 1` | Every other session is returning. |
| New user | A user whose first observed session has `ga_session_number = 1` | Users first observed with a higher session number were active before 1 November 2020 and are excluded from activation and cohort analysis. |
| Order | A distinct `ecommerce.transaction_id` on a `purchase` event that is not NULL, blank or a placeholder, with revenue above zero | Duplicate purchase events for one transaction are deduplicated with `QUALIFY row_number()`, keeping the earliest event. |
| First-touch channel | Grouping of the user's `traffic_source.source` and `traffic_source.medium` | This is how the user was first acquired, not the source of the current visit. Always labelled "first-touch channel". |

First-touch channel grouping:

| Channel | Rule |
|---|---|
| Organic Search | medium `organic` |
| Paid Search | medium `cpc` |
| Direct | source `(direct)` and medium `(none)` |
| Referral | medium `referral` |
| Unknown | medium `<Other>` or `(data deleted)`; obfuscated by Google and kept as its own group |

Market: `United States`, `India`, or `Rest of world` (all other countries, including placeholder countries).

## Time

- `event_timestamp` is microseconds since epoch in UTC. It is used for ordering events and for the 30-day window.
- `event_date` is the property's reporting date. It is used for daily, weekly and monthly reporting.
- The two are never mixed in one calculation. All DuckDB connections set `TimeZone = 'UTC'`.

## Metrics

| Metric | Definition |
|---|---|
| Funnel step reached | The session has at least one event of that type, in this order: session → `view_item` → `add_to_cart` → `begin_checkout` → `add_payment_info` → order. The top step is every session (5,272 sessions have no `session_start` event and are still sessions). The last step is a valid order rather than a raw `purchase` event, so the funnel's last bar equals session conversion. This is not a strict sequence. Sessions that reach a later step without an earlier one are counted in `docs/cleaning_log.md`. |
| Step conversion | Sessions reaching step *k* ÷ sessions reaching step *k − 1* |
| Session conversion | Sessions with an order ÷ all sessions |
| AOV | Order revenue ÷ orders |
| Revenue per session | Order revenue ÷ sessions |
| Revenue at stake | Extra revenue per 30 days if one step's conversion rose by 1 percentage point with every other step unchanged. Base: marginal sessions convert downstream like current ones. Low: they convert downstream at half the current rate. High: base, at the December run rate. |
| Activated user | A new user who adds to cart in their first session. Module 4 tests whether this predicts purchase. |
| 30-day purchase | The user has an order within 30 days (30 × 24 hours of UTC time) of the first session's first event. Only users first seen on or before 1 January 2021 count, so everyone has a full 30-day window inside the data. |
| Weekly retention | Share of a weekly new-user cohort with at least one session in week *k* after the first session's week. Weeks start Monday on property dates. |
| North star | Weekly purchasing users (distinct users with an order that week). Guardrails: AOV and revenue per session. |

## Placeholders

`<Other>`, `(data deleted)`, `(not set)`, NULL and `''` are Google's obfuscation or missing-value markers. They are counted in `docs/cleaning_log.md` and kept as their own groups. Rows are excluded only when a definition above requires a valid value, such as an order needing a real `transaction_id`.
