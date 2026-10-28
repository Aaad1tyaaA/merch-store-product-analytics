-- Read-only inspection of the extracted DuckDB tables.
SET memory_limit = '512MB';
SET threads = 1;
SET TimeZone = 'UTC';

-- 1. Coverage controls. These are raw counts, not sessions or deduplicated orders.
SELECT
    COUNT(*) AS event_occurrences,
    COUNT(DISTINCT user_pseudo_id) AS raw_distinct_user_ids,
    COUNT(DISTINCT event_date) AS property_dates,
    MIN(event_date) AS first_property_date,
    MAX(event_date) AS last_property_date,
    COUNT(DISTINCT event_name) AS event_types,
    (SELECT COUNT(*) FROM main.items_flat) AS item_occurrences
FROM main.events_flat;

-- 2. Event inventory, used to establish which funnel steps are observable.
SELECT event_name, COUNT(*) AS event_occurrences
FROM main.events_flat
GROUP BY event_name
ORDER BY event_occurrences DESC, event_name;

-- 3. Session-metadata coverage. Missing IDs remain in the raw data.
SELECT
    COUNT(*) FILTER (WHERE ga_session_id IS NULL) AS missing_integer_session_id,
    COUNT(*) FILTER (WHERE ga_session_id_text IS NOT NULL) AS string_session_id_present,
    COUNT(*) FILTER (WHERE ga_session_number IS NULL) AS missing_integer_session_number,
    COUNT(*) FILTER (WHERE source_duplicate_ordinal > 1) AS exact_source_repeat_occurrences
FROM main.events_flat;

-- 4. Purchase metadata, before an explicit transaction deduplication policy.
SELECT
    COUNT(*) AS purchase_events,
    COUNT(DISTINCT transaction_id) AS distinct_raw_transaction_ids,
    COUNT(*) FILTER (WHERE transaction_id IS NULL) AS null_transaction_id,
    COUNT(*) FILTER (WHERE transaction_id = '') AS blank_transaction_id,
    COUNT(*) FILTER (WHERE transaction_id IN ('<Other>', '(data deleted)', '(not set)')) AS placeholder_transaction_id,
    SUM(purchase_revenue_usd) AS raw_purchase_event_revenue_usd
FROM main.events_flat
WHERE event_name = 'purchase';

-- 5. Month-by-month controls against the saved BigQuery preflight.
SELECT
    substr(source_table_suffix, 1, 6) AS source_month,
    COUNT(*) AS event_occurrences,
    SUM(n_items) AS expected_item_occurrences,
    COUNT(*) FILTER (WHERE event_name = 'purchase') AS purchase_events,
    SUM(purchase_revenue_usd) FILTER (WHERE event_name = 'purchase') AS raw_purchase_event_revenue_usd
FROM main.events_flat
GROUP BY source_month
ORDER BY source_month;

-- 6. Purchase events by transaction-id validity. Orders need a valid id and revenue.
SELECT
    CASE WHEN transaction_id IS NULL THEN 'NULL'
         WHEN trim(transaction_id) = '' THEN 'blank'
         WHEN transaction_id IN ('(not set)', '<Other>', '(data deleted)') THEN transaction_id
         ELSE 'valid' END AS transaction_id_status,
    purchase_revenue_usd > 0 AS has_revenue,
    COUNT(*) AS purchase_events,
    COUNT(DISTINCT transaction_id) AS distinct_ids,
    SUM(purchase_revenue_usd) AS revenue_usd
FROM main.events_flat
WHERE event_name = 'purchase'
GROUP BY ALL
ORDER BY ALL;

-- 7. First-touch source and medium as recorded, including obfuscated values.
SELECT first_source, first_medium, COUNT(DISTINCT user_pseudo_id) AS users, COUNT(*) AS events
FROM main.events_flat
GROUP BY ALL
ORDER BY users DESC;

-- 8. Top countries by users.
SELECT country, COUNT(DISTINCT user_pseudo_id) AS users, COUNT(*) AS events
FROM main.events_flat
GROUP BY country
ORDER BY users DESC
LIMIT 15;

-- 9. Session key choice: ga_session_id alone merges different users' sessions.
SELECT
    (SELECT COUNT(*) FROM (SELECT DISTINCT user_pseudo_id, ga_session_id FROM main.events_flat)) AS user_plus_session_id,
    (SELECT COUNT(DISTINCT ga_session_id) FROM main.events_flat) AS session_id_alone,
    (SELECT COUNT(*) FROM main.events_flat WHERE event_name = 'session_start') AS session_start_events;
