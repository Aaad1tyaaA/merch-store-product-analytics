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
    event_date AS event_date_raw,
    PARSE_DATE('%Y%m%d', event_date) AS event_date,
    event_timestamp AS event_timestamp_micros,
    TIMESTAMP_MICROS(event_timestamp) AS event_ts,
    event_previous_timestamp,
    event_bundle_sequence_id,
    event_name,
    user_pseudo_id,
    (SELECT value.int_value FROM UNNEST(event_params)
        WHERE key = 'ga_session_id') AS ga_session_id,
    (SELECT value.string_value FROM UNNEST(event_params)
        WHERE key = 'ga_session_id') AS ga_session_id_text,
    (SELECT value.int_value FROM UNNEST(event_params)
        WHERE key = 'ga_session_number') AS ga_session_number,
    (SELECT value.string_value FROM UNNEST(event_params)
        WHERE key = 'ga_session_number') AS ga_session_number_text,
    (SELECT value.int_value FROM UNNEST(event_params)
        WHERE key = 'engagement_time_msec') AS engagement_time_msec,
    (SELECT value.string_value FROM UNNEST(event_params)
        WHERE key = 'page_title') AS page_title,
    traffic_source.source AS first_source,
    traffic_source.medium AS first_medium,
    traffic_source.name AS first_campaign,
    device.category AS device_category,
    device.operating_system AS os,
    device.web_info.browser AS browser,
    geo.country AS country,
    ecommerce.transaction_id AS transaction_id,
    ecommerce.purchase_revenue_in_usd AS purchase_revenue_usd,
    ecommerce.total_item_quantity AS total_item_quantity,
    ARRAY_LENGTH(items) AS n_items,
    TO_JSON_STRING(ARRAY(
        SELECT DISTINCT i.promotion_name
        FROM UNNEST(items) AS i
        ORDER BY i.promotion_name
    )) AS promotion_names_json
FROM numbered_events;
