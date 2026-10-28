SELECT
    SUBSTR(_TABLE_SUFFIX, 1, 6) AS source_month,
    COUNT(*) AS event_rows,
    COUNT(DISTINCT event_date) AS property_dates,
    SUM(COALESCE(ARRAY_LENGTH(items), 0)) AS item_rows,
    COUNTIF(event_date != _TABLE_SUFFIX
        OR SAFE.PARSE_DATE('%Y%m%d', event_date) IS NULL) AS invalid_property_dates,
    COUNTIF(EXISTS (
        SELECT 1
        FROM UNNEST(event_params) AS p
        WHERE p.key IN (
            'ga_session_id', 'ga_session_number',
            'engagement_time_msec', 'page_title'
        )
        GROUP BY p.key
        HAVING COUNT(*) > 1
    )) AS events_with_repeated_selected_keys,
    COUNTIF(event_name = 'purchase') AS purchase_events,
    COUNTIF(event_name = 'purchase'
        AND ecommerce.purchase_revenue_in_usd IS NULL) AS purchase_events_without_revenue,
    SUM(IF(event_name = 'purchase',
        ecommerce.purchase_revenue_in_usd, 0)) AS raw_purchase_revenue_usd
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
GROUP BY source_month
ORDER BY source_month;
