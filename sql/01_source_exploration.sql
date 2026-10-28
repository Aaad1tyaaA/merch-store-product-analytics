-- Source coverage and identifier quality.
SELECT
    COUNT(*) AS event_count,
    COUNT(DISTINCT user_pseudo_id) AS distinct_user_ids_raw,
    COUNT(DISTINCT event_date) AS day_count,
    COUNT(DISTINCT event_name) AS event_type_count,
    MIN(event_date) AS first_property_date,
    MAX(event_date) AS last_property_date,
    COUNTIF(user_pseudo_id IS NULL) AS null_user_id_events,
    COUNTIF(user_pseudo_id = '') AS blank_user_id_events,
    COUNTIF(user_pseudo_id = '<Other>') AS other_user_id_events,
    COUNTIF(user_pseudo_id = '(data deleted)') AS deleted_user_id_events
FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20210131';


-- Event inventory.
SELECT
    event_name,
    COUNT(*) AS event_count
FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE
    _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
GROUP BY
    event_name
ORDER BY
    event_count DESC,
    event_name;


-- Parameter inventory for one day.
SELECT
    e.event_name,
    p.key AS parameter_key,
    COUNT(*) AS parameter_entries
FROM
    `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_20210131` AS e
CROSS JOIN
    UNNEST(e.event_params) AS p
GROUP BY
    e.event_name,
    p.key
ORDER BY
    parameter_entries DESC,
    e.event_name,
    parameter_key
LIMIT 30;
