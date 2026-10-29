# Cleaning log

Every rule applied between the raw extraction and the analytical model, with the rows it affects. Raw tables (`events_flat`, `items_flat`) are never modified; rules live in `sql/02_model.sql`. Counts come from `01_source_exploration.ipynb` and `02_session_model.ipynb`.

## Source controls

| Control | Count | Expected |
|---|---:|---:|
| Events | 4,295,584 | 4,295,584 |
| `user_pseudo_id` values | 270,154 | 270,154 |
| Property dates | 92 | 92 |
| Event types | 17 | 17 |
| Item occurrences (all item-bearing events) | 3,982,732 | from BigQuery preflight |
| Exact duplicate source rows | 0 | |

## Placeholders, counted and kept

Event-level counts in `events_flat` (4,295,584 rows). Full per-column profile: `docs/verification/placeholder_profile.json`.

| Column | NULL | `<Other>` | `(data deleted)` | `(not set)` | Treatment |
|---|---:|---:|---:|---:|---|
| `first_source` | 0 | 1,131,013 | 308,695 | 0 | Kept; channel grouping uses medium first |
| `first_medium` | 0 | 597,482 | 313,917 | 0 | Kept as channel "Unknown" |
| `first_campaign` | 0 | 782,379 | 306,045 | 0 | Not used |
| `country` | 0 | 0 | 0 | 32,208 | Kept in market "Rest of world" |
| `os` / `browser` | 0 | 110,323 / 114,439 | 0 | 0 | Not used |
| `page_title` | 20,948 | 0 | 0 | 0 | Not used |
| `transaction_id` | 3,549,275 | 0 | 0 | 741,523 | Non-purchase events carry no id; see orders below |

In `items_flat`, `item_category` has 148,459 `(not set)` and 16,397 blank values, grouped as category "Unknown". `promotion_name` is `(not set)` on 3,771,791 item rows, because only promotion events carry it.

## Sessions

| Rule | Rows affected | Decision |
|---|---:|---|
| Events without `ga_session_id` | 0 | None to exclude |
| Session key = `user_pseudo_id` + `ga_session_id` | 360,129 sessions | Keying on `ga_session_id` alone gives 349,545, merging 10,584 sessions of different users |
| Sessions without a `session_start` event | 5,272 | Kept. 26 of them span two property dates. `session_start` events total 354,970 |
| Sessions spanning two property dates | 845 | Kept, reported on the date of their first event |
| Sessions with more than one device, country or first-touch value | 0 | Session attributes are exact |
| Sessions with more than one `session_start` | 105 | Kept; presence flag only |

## Orders

| Rule | Purchase events | Revenue, USD | Decision |
|---|---:|---:|---|
| All purchase events | 5,692 | 362,165 | Raw control |
| `transaction_id` = `(not set)`, with revenue | 433 | 30,489 | Excluded: cannot be told apart or deduplicated |
| `transaction_id` = `(not set)`, zero revenue | 450 | 0 | Excluded |
| `transaction_id` NULL | 23 | 1,328 | Excluded |
| Valid id, positive revenue | 4,786 | 330,348 | Candidate orders |
| Repeat events for an id already counted | 335 | 22,708 | Removed by `QUALIFY row_number()`, keeping the earliest event |
| **Orders** | **4,451** | **307,640** | One row per `transaction_id` |

326 ids appear on more than one purchase event. For 311 of them every repeat is in the same user and session; 15 ids appear for two different users up to 56 days apart with different revenue. Those 15 are kept as one order each (the earliest), consistent with GA4 counting transactions by distinct id. Excluded purchase revenue (31,817 USD with an invalid id, 22,708 USD duplicated) is 15.1% of raw purchase-event revenue, which is the main reason this revenue differs from a sum over purchase events.

## Funnel order gaps (session level)

The funnel counts presence, not sequence. Sessions that reached a step without the one before it:

| Gap | Sessions |
|---|---:|
| `add_to_cart` without `view_item` | 15 |
| `begin_checkout` without `add_to_cart` | 5,145 (2,790 of them in new sessions, so not only carts carried over from an earlier visit) |
| `add_payment_info` without `begin_checkout` | 2 |
| Order without `add_payment_info` | 0 |
| Order without `begin_checkout` | 0 |
| `purchase` event but no valid order | 815 |

Every bar of the funnel still shrinks (checked in `tests/`), so presence counts are used without forcing a sequence.

## Users

| Rule | Users | Decision |
|---|---:|---|
| First observed session has `ga_session_number` > 1 | 9,288 | Not new users: excluded from activation, 30-day purchase and cohorts |
| Activation eligibility | First seen 26 Nov–26 Dec 2020 | New users only; exclude first-session buyers in the predictive analysis. Later arrivals lack a full reliable 30-day follow-up; earlier arrivals lack reliable cart tracking |
| More than one first-touch channel across events | 39,900 | User channel = most frequent value (`mode`), ties alphabetical. Obfuscation changes `traffic_source` within a user |
| More than one device category | 4,182 | User device = most frequent value |
| More than one country | 0 | |

## Time zones

`event_date` equals the UTC date of `event_timestamp` for every event in this sample. DuckDB otherwise renders timestamps in the machine's time zone (IST here, which moved 993,380 events to a different date), so every connection sets `TimeZone = 'UTC'`.
