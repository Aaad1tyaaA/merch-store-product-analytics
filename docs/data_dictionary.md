# Raw data dictionary

## `events_flat`

Grain: one source event occurrence. All event types in the three-month window are retained.

| Field or group | Meaning |
|---|---|
| `event_id` | Extraction surrogate: daily suffix, full-record SHA-256 and ordinal among identical source records |
| `source_table_suffix` | Original daily table suffix, `YYYYMMDD` |
| `source_event_fingerprint` | SHA-256 of the complete source record serialized by BigQuery |
| `source_duplicate_ordinal` | Starts at 1 within identical full records; larger ordinals retain exact repeats |
| `event_date_raw`, `event_date` | Original property date string and its parsed date |
| `event_timestamp_micros`, `event_ts` | Original event microseconds and equivalent UTC timestamp |
| `event_previous_timestamp`, `event_bundle_sequence_id` | Source ordering metadata; neither is assumed to be a unique event key |
| `event_name` | Source event type |
| `user_pseudo_id` | Pseudonymous source identifier, not a verified person ID |
| `ga_session_id`, `ga_session_number` | Integer-valued source parameters; no reconstructed session key yet |
| `ga_session_id_text`, `ga_session_number_text` | String-valued forms retained for data-quality inspection |
| `engagement_time_msec`, `page_title` | Selected event parameters, preserving missing values |
| `first_source`, `first_medium`, `first_campaign` | Source first-touch acquisition fields; not current-session attribution |
| `device_category`, `os`, `browser`, `country` | Source context, including missing or obfuscated labels |
| `transaction_id` | Original ecommerce transaction identifier; validity and uniqueness are not assumed |
| `purchase_revenue_usd` | Source ecommerce purchase revenue in USD, before order deduplication |
| `total_item_quantity` | Source ecommerce quantity field; not used to infer item-array length |
| `n_items` | Original number of elements in the event's `items` array |
| `promotion_names_json` | JSON array of distinct item-level promotion names; not an attributed campaign |

## `items_flat`

Grain: one source item-array occurrence. The compound key is (`event_id`, `item_offset`). Repeated products at different offsets are retained. The table includes every item-bearing event type, not just purchase events, so its total revenue must not be used as order revenue without an explicit filter and deduplication policy.

| Field or group | Meaning |
|---|---|
| `event_id` | Parent occurrence key from the identical event-key construction |
| `source_table_suffix`, `source_event_fingerprint`, `source_duplicate_ordinal` | Parent source identity components |
| `item_offset` | Zero-based position in the original array |
| `event_date_raw`, `event_date`, `event_ts`, `event_name` | Parent date, time and event context |
| `user_pseudo_id`, `ga_session_id`, `transaction_id` | Parent identifiers, retaining original missing values |
| `item_id`, `item_name`, `item_brand`, `item_variant`, `item_category` | Source product descriptors |
| `price_usd`, `quantity`, `item_revenue_usd` | Source item-level measures; not recomputed from one another |
| `promotion_id`, `promotion_name`, `creative_name`, `creative_slot` | Source promotion and creative labels |

Google documents the dataset's obfuscation and limited internal consistency in its [sample dataset guide](https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset). Missing values and placeholders are measured in `docs/verification/placeholder_profile.json`, not silently normalized at extraction.

## Analytical model

Built by `sql/02_model.sql` and `sql/03_metrics.sql`. Definitions: `docs/metric_definitions.md`; rules and row counts: `docs/cleaning_log.md`.

| Table | Grain | Key fields |
|---|---|---|
| `fact_events` (view) | one source event | `session_key` = `user_pseudo_id` + `ga_session_id`, first-touch `channel`, `market` |
| `fact_sessions` | one session | step flags (`has_view_item` … `has_order`), `orders`, `revenue_usd`, `is_new_session`, `in_funnel_window`, `in_order_window` |
| `fact_transactions` | one order (valid, deduplicated `transaction_id`) | `revenue_usd`, `order_ts`, `session_key` |
| `dim_users` | one `user_pseudo_id` | most frequent device, country and channel; first-session flags; `is_new_user`, `in_activation_cohort`, `purchased_30d`, `revenue_56d` |
| `funnel_overall`, `funnel_by_segment` | one step (per segment) | sessions reaching the step and step conversion, funnel window |
| `revenue_at_stake` | one step | USD per 30 days from +1 point, low / base / high |
| `weekly_north_star`, `retention_cohorts` | one week / cohort-week | purchasing users with guardrails; weekly retention of new users |
| `channel_quality`, `promo_effect`, `category_funnel` | one channel / one row / one category | first-touch channel shares; promotion raw vs adjusted gap; category funnel |
