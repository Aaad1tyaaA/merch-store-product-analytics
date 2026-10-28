-- Session, order and user model built on the raw events_flat table.
-- Session key: user_pseudo_id + ga_session_id. ga_session_id alone collides across users.
-- Tracking windows (property dates), from the daily event inventory in 02_session_model.ipynb:
--   add_to_cart is missing 1-15 and 21-24 Nov 2020, so funnel metrics use 26 Nov 2020 - 25 Jan 2021.
--   valid transaction ids are missing before 11 Nov 2020 and mostly after 25 Jan 2021,
--   so order metrics use 12 Nov 2020 - 25 Jan 2021.
SET TimeZone = 'UTC';

CREATE OR REPLACE VIEW fact_events AS
SELECT
    event_id,
    user_pseudo_id || '-' || CAST(ga_session_id AS VARCHAR) AS session_key,
    user_pseudo_id,
    ga_session_id,
    ga_session_number,
    event_name,
    event_ts,       -- UTC, for ordering and windows
    event_date,     -- property date, for reporting
    engagement_time_msec,
    first_source,
    first_medium,
    CASE
        WHEN first_medium = 'organic' THEN 'Organic Search'
        WHEN first_medium = 'cpc' THEN 'Paid Search'
        WHEN first_source = '(direct)' AND first_medium = '(none)' THEN 'Direct'
        WHEN first_medium = 'referral' THEN 'Referral'
        ELSE 'Unknown'
    END AS channel,
    device_category,
    country,
    CASE country WHEN 'United States' THEN 'United States' WHEN 'India' THEN 'India' ELSE 'Rest of world' END AS market,
    transaction_id,
    purchase_revenue_usd,
    total_item_quantity
FROM events_flat;

-- One row per order: valid transaction id, positive revenue, earliest event kept.
CREATE OR REPLACE TABLE fact_transactions AS
SELECT
    transaction_id,
    event_id,
    session_key,
    user_pseudo_id,
    event_ts AS order_ts,
    event_date AS order_date,
    purchase_revenue_usd AS revenue_usd,
    total_item_quantity AS quantity
FROM fact_events
WHERE event_name = 'purchase'
  AND transaction_id IS NOT NULL
  AND trim(transaction_id) <> ''
  AND transaction_id NOT IN ('(not set)', '<Other>', '(data deleted)')
  AND purchase_revenue_usd > 0
QUALIFY row_number() OVER (PARTITION BY transaction_id ORDER BY event_ts, event_id) = 1;

-- Device, country and first-touch fields are constant within a session in this data
-- (checked in tests), so any_value is exact here.
CREATE OR REPLACE TABLE fact_sessions AS
WITH s AS (
    SELECT
        session_key,
        any_value(user_pseudo_id) AS user_pseudo_id,
        any_value(ga_session_id) AS ga_session_id,
        min(ga_session_number) AS ga_session_number,
        min(event_ts) AS session_start_ts,
        min(event_date) AS session_date,
        any_value(device_category) AS device_category,
        any_value(country) AS country,
        any_value(market) AS market,
        any_value(channel) AS channel,
        count(*) AS events,
        coalesce(sum(engagement_time_msec), 0) / 1000.0 AS engagement_sec,
        count(*) FILTER (WHERE event_name = 'page_view') AS page_views,
        bool_or(event_name = 'session_start') AS has_session_start,
        bool_or(event_name = 'view_item') AS has_view_item,
        bool_or(event_name = 'add_to_cart') AS has_add_to_cart,
        bool_or(event_name = 'begin_checkout') AS has_begin_checkout,
        bool_or(event_name = 'add_payment_info') AS has_add_payment_info,
        bool_or(event_name = 'purchase') AS has_purchase_event,
        bool_or(event_name = 'select_promotion') AS has_select_promotion
    FROM fact_events
    GROUP BY session_key
), o AS (
    SELECT session_key, count(*) AS orders, sum(revenue_usd) AS revenue_usd
    FROM fact_transactions GROUP BY session_key
)
SELECT
    s.*,
    s.ga_session_number = 1 AS is_new_session,
    coalesce(o.orders, 0) AS orders,
    coalesce(o.revenue_usd, 0) AS revenue_usd,
    coalesce(o.orders, 0) > 0 AS has_order,
    s.session_date BETWEEN DATE '2020-11-26' AND DATE '2021-01-25' AS in_funnel_window,
    s.session_date BETWEEN DATE '2020-11-12' AND DATE '2021-01-25' AS in_order_window
FROM s LEFT JOIN o USING (session_key);

-- One row per user. Device and first-touch channel vary across a user's events in
-- the obfuscated sample, so the user's most frequent value is used (ties: alphabetical).
CREATE OR REPLACE TABLE dim_users AS
WITH first_session AS (
    SELECT *
    FROM fact_sessions
    QUALIFY row_number() OVER (PARTITION BY user_pseudo_id ORDER BY session_start_ts, session_key) = 1
), user_mode AS (
    SELECT user_pseudo_id, attribute, value
    FROM (
        SELECT user_pseudo_id, 'device' AS attribute, device_category AS value, count(*) AS n FROM fact_events GROUP BY ALL
        UNION ALL
        SELECT user_pseudo_id, 'country', country, count(*) FROM fact_events GROUP BY ALL
        UNION ALL
        SELECT user_pseudo_id, 'channel', channel, count(*) FROM fact_events GROUP BY ALL
    )
    QUALIFY row_number() OVER (PARTITION BY user_pseudo_id, attribute ORDER BY n DESC, value) = 1
), modes AS (
    PIVOT user_mode ON attribute IN ('device', 'country', 'channel') USING any_value(value) GROUP BY user_pseudo_id
), orders AS (
    SELECT t.user_pseudo_id,
           count(*) AS orders,
           sum(t.revenue_usd) AS revenue_usd,
           count(*) FILTER (WHERE t.order_ts < f.session_start_ts + INTERVAL 30 DAY) AS orders_30d,
           coalesce(sum(t.revenue_usd) FILTER (WHERE t.order_ts < f.session_start_ts + INTERVAL 30 DAY), 0) AS revenue_30d,
           coalesce(sum(t.revenue_usd) FILTER (WHERE t.order_ts < f.session_start_ts + INTERVAL 56 DAY), 0) AS revenue_56d
    FROM fact_transactions t JOIN first_session f USING (user_pseudo_id)
    GROUP BY t.user_pseudo_id
), sessions AS (
    SELECT user_pseudo_id, count(*) AS sessions FROM fact_sessions GROUP BY 1
)
SELECT
    f.user_pseudo_id,
    f.session_key AS first_session_key,
    f.session_start_ts AS first_seen_ts,
    f.session_date AS first_seen_date,
    f.ga_session_number = 1 AS is_new_user,
    -- first session has add_to_cart tracking and a full 30-day order window inside the data
    f.session_date BETWEEN DATE '2020-11-26' AND DATE '2020-12-26' AS in_activation_cohort,
    m.device AS device_category,
    m.country,
    CASE m.country WHEN 'United States' THEN 'United States' WHEN 'India' THEN 'India' ELSE 'Rest of world' END AS market,
    m.channel,
    f.device_category AS first_session_device,
    f.channel AS first_session_channel,
    f.market AS first_session_market,
    f.has_view_item AS first_session_viewed_item,
    f.has_add_to_cart AS activated,
    f.has_begin_checkout AS first_session_began_checkout,
    f.has_order AS first_session_ordered,
    f.engagement_sec AS first_session_engagement_sec,
    f.page_views AS first_session_page_views,
    s.sessions,
    coalesce(o.orders, 0) AS orders,
    coalesce(o.revenue_usd, 0) AS revenue_usd,
    coalesce(o.orders_30d, 0) > 0 AS purchased_30d,
    coalesce(o.revenue_30d, 0) AS revenue_30d,
    coalesce(o.revenue_56d, 0) AS revenue_56d
FROM first_session f
JOIN modes m USING (user_pseudo_id)
JOIN sessions s USING (user_pseudo_id)
LEFT JOIN orders o USING (user_pseudo_id);
