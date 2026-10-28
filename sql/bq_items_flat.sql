-- Identical source rows retain separate ordinals; the key is an extraction surrogate.
WITH source_events AS (
    SELECT
        _TABLE_SUFFIX AS source_table_suffix,
        TO_HEX(SHA256(TO_JSON_STRING(t))) AS source_event_fingerprint,
        t.*
    FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` AS t
    WHERE _TABLE_SUFFIX BETWEEN @start AND @end
), numbered_events AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY source_table_suffix, source_event_fingerprint
            ORDER BY event_timestamp
        ) AS source_duplicate_ordinal
    FROM source_events
)
SELECT
    CONCAT(source_table_suffix, ':', source_event_fingerprint, ':',
        CAST(source_duplicate_ordinal AS STRING)) AS event_id,
    source_table_suffix,
    source_event_fingerprint,
    source_duplicate_ordinal,
    item_offset,
    event_date AS event_date_raw,
    PARSE_DATE('%Y%m%d', event_date) AS event_date,
    TIMESTAMP_MICROS(event_timestamp) AS event_ts,
    event_name,
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params)
        WHERE key = 'ga_session_id') AS ga_session_id,
    ecommerce.transaction_id AS transaction_id,
    i.item_id,
    i.item_name,
    i.item_brand,
    i.item_variant,
    i.item_category,
    i.price_in_usd AS price_usd,
    i.quantity,
    i.item_revenue_in_usd AS item_revenue_usd,
    i.promotion_id,
    i.promotion_name,
    i.creative_name,
    i.creative_slot
FROM numbered_events
CROSS JOIN UNNEST(items) AS i WITH OFFSET AS item_offset;
