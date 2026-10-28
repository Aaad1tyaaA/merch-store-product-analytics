-- Reporting tables built from the model. Definitions: docs/metric_definitions.md.
SET TimeZone = 'UTC';

-- Session-level funnel in long form: one row per session and step reached.
CREATE OR REPLACE VIEW session_steps AS
SELECT s.*, st.step_order, st.step
FROM fact_sessions s
CROSS JOIN (VALUES (1, 'Session'), (2, 'View item'), (3, 'Add to cart'),
                   (4, 'Begin checkout'), (5, 'Add payment info'), (6, 'Order')) st(step_order, step)
WHERE s.in_funnel_window AND CASE st.step_order
        WHEN 1 THEN true
        WHEN 2 THEN s.has_view_item
        WHEN 3 THEN s.has_add_to_cart
        WHEN 4 THEN s.has_begin_checkout
        WHEN 5 THEN s.has_add_payment_info
        WHEN 6 THEN s.has_order
      END;

CREATE OR REPLACE TABLE funnel_overall AS
WITH f AS (
    SELECT step_order, step, count(*) AS sessions FROM session_steps GROUP BY ALL
)
SELECT
    step_order,
    step,
    sessions,
    sessions / first_value(sessions) OVER (ORDER BY step_order) AS share_of_sessions,
    sessions / lag(sessions) OVER (ORDER BY step_order) AS step_conversion,
    lag(sessions) OVER (ORDER BY step_order) - sessions AS sessions_lost
FROM f
ORDER BY step_order;

-- Same funnel for each segment of four dimensions.
CREATE OR REPLACE TABLE funnel_by_segment AS
WITH seg AS (
    SELECT step_order, step, 'Device' AS dimension, device_category AS segment FROM session_steps
    UNION ALL SELECT step_order, step, 'Market', market FROM session_steps
    UNION ALL SELECT step_order, step, 'First-touch channel', channel FROM session_steps
    UNION ALL SELECT step_order, step, 'New vs returning',
                     CASE WHEN is_new_session THEN 'New' ELSE 'Returning' END FROM session_steps
), f AS (
    SELECT dimension, segment, step_order, step, count(*) AS sessions FROM seg GROUP BY ALL
)
SELECT
    dimension, segment, step_order, step, sessions,
    sessions / first_value(sessions) OVER w AS share_of_sessions,
    sessions / lag(sessions) OVER w AS step_conversion
FROM f
WINDOW w AS (PARTITION BY dimension, segment ORDER BY step_order)
ORDER BY dimension, segment, step_order;

-- Revenue per 30 days from +1 percentage point on one step's conversion.
-- Extra orders = sessions entering the step x 0.01 x P(order | reached step) x downstream factor.
CREATE OR REPLACE TABLE revenue_at_stake AS
WITH periods AS (
    SELECT 'all' AS period, * FROM fact_sessions WHERE in_funnel_window
    UNION ALL
    SELECT 'december', * FROM fact_sessions WHERE session_date BETWEEN DATE '2020-12-01' AND DATE '2020-12-31'
), days AS (
    SELECT period, count(DISTINCT session_date) AS days, sum(orders) AS orders, sum(revenue_usd) AS revenue
    FROM periods GROUP BY period
), steps AS (
    SELECT p.period, st.step_order, st.step,
           count(*) FILTER (WHERE CASE st.step_order
               WHEN 1 THEN true WHEN 2 THEN has_view_item WHEN 3 THEN has_add_to_cart
               WHEN 4 THEN has_begin_checkout WHEN 5 THEN has_add_payment_info WHEN 6 THEN has_order END) AS sessions
    FROM periods p
    CROSS JOIN (VALUES (1, 'Session'), (2, 'View item'), (3, 'Add to cart'),
                       (4, 'Begin checkout'), (5, 'Add payment info'), (6, 'Order')) st(step_order, step)
    GROUP BY ALL
), calc AS (
    SELECT s.period, s.step_order, s.step, s.sessions,
           lag(s.sessions) OVER (PARTITION BY s.period ORDER BY s.step_order) AS entering,
           d.orders, d.revenue, d.days,
           d.revenue / d.orders AS aov
    FROM steps s JOIN days d USING (period)
), usd AS (
    SELECT *,
           sessions / entering AS step_conversion,
           1 - sessions / entering AS drop_rate,
           entering * 0.01 * (orders / sessions) * aov * 30.0 / days AS usd_per_30d
    FROM calc WHERE step_order > 1
)
SELECT
    a.step_order,
    a.step,
    a.step_conversion,
    a.drop_rate,
    a.usd_per_30d * CASE WHEN a.step_order = 6 THEN 1.0 ELSE 0.5 END AS usd_low,
    a.usd_per_30d AS usd_base,
    d.usd_per_30d AS usd_high,
    rank() OVER (ORDER BY a.usd_per_30d DESC) AS rank_by_usd,
    rank() OVER (ORDER BY a.drop_rate DESC) AS rank_by_drop,
    rank() OVER (ORDER BY a.entering - a.sessions DESC) AS rank_by_sessions_lost
FROM usd a JOIN usd d ON d.period = 'december' AND d.step_order = a.step_order
WHERE a.period = 'all'
ORDER BY a.step_order;

-- Weekly north star with guardrails, on property dates. Weeks start Monday.
-- Only full weeks inside the order window.
CREATE OR REPLACE TABLE weekly_north_star AS
WITH s AS (
    SELECT date_trunc('week', session_date) AS week, count(DISTINCT session_date) AS days, count(*) AS sessions,
           sum(orders) AS orders, sum(revenue_usd) AS revenue_usd
    FROM fact_sessions GROUP BY 1
), b AS (
    SELECT date_trunc('week', order_date) AS week, count(DISTINCT user_pseudo_id) AS purchasing_users
    FROM fact_transactions GROUP BY 1
)
SELECT week, days, purchasing_users, sessions, orders, revenue_usd,
       revenue_usd / orders AS aov, revenue_usd / sessions AS revenue_per_session
FROM s JOIN b USING (week)
WHERE week >= DATE '2020-11-12' AND week + INTERVAL 6 DAY <= DATE '2021-01-25'
ORDER BY week;

-- Weekly retention of new users: share with a session k weeks after their first week.
CREATE OR REPLACE TABLE retention_cohorts AS
WITH u AS (
    SELECT user_pseudo_id, date_trunc('week', first_seen_date) AS cohort_week FROM dim_users WHERE is_new_user
), a AS (
    SELECT DISTINCT s.user_pseudo_id, u.cohort_week,
           date_diff('week', u.cohort_week, date_trunc('week', s.session_date)) AS week_number
    FROM fact_sessions s JOIN u USING (user_pseudo_id)
), size AS (
    SELECT cohort_week, count(*) AS cohort_users FROM u GROUP BY 1
)
SELECT a.cohort_week, size.cohort_users, a.week_number,
       count(*) AS active_users, count(*) / size.cohort_users AS retention
FROM a JOIN size USING (cohort_week)
GROUP BY a.cohort_week, size.cohort_users, a.week_number
ORDER BY cohort_week, week_number;

-- New users first seen 12-30 November, each followed for exactly 56 days of order tracking.
CREATE OR REPLACE TABLE channel_quality AS
WITH u AS (
    SELECT channel, count(*) AS users, sum(revenue_56d) AS revenue_56d,
           count(*) FILTER (WHERE revenue_56d > 0) AS buyers_56d
    FROM dim_users
    WHERE is_new_user AND first_seen_date BETWEEN DATE '2020-11-12' AND DATE '2020-11-30'
    GROUP BY channel
)
SELECT channel, users, buyers_56d, revenue_56d,
       users / sum(users) OVER () AS share_of_users,
       revenue_56d / sum(revenue_56d) OVER () AS share_of_revenue,
       buyers_56d / users AS buyer_rate_56d,
       revenue_56d / users AS revenue_per_user_56d
FROM u
ORDER BY users DESC;

-- Sessions that clicked a promotion vs not: raw gap and gap standardized to the
-- overall device x new/returning session mix. Observational, not a causal effect.
CREATE OR REPLACE TABLE promo_effect AS
WITH cell AS (
    SELECT device_category, is_new_session, has_select_promotion,
           count(*) AS sessions, avg(has_order::INT) AS conversion
    FROM fact_sessions WHERE in_funnel_window GROUP BY ALL
), weights AS (
    SELECT device_category, is_new_session, sum(sessions) / (SELECT sum(sessions) FROM cell) AS weight
    FROM cell GROUP BY ALL
), arms AS (
    SELECT has_select_promotion,
           sum(sessions) AS sessions,
           sum(sessions * conversion) / sum(sessions) AS raw_conversion,
           sum(w.weight * conversion) / sum(w.weight) AS adjusted_conversion
    FROM cell JOIN weights w USING (device_category, is_new_session)
    GROUP BY has_select_promotion
)
SELECT
    p.sessions AS promo_sessions, n.sessions AS other_sessions,
    p.raw_conversion AS promo_raw_conversion, n.raw_conversion AS other_raw_conversion,
    p.raw_conversion - n.raw_conversion AS raw_gap,
    p.adjusted_conversion AS promo_adjusted_conversion, n.adjusted_conversion AS other_adjusted_conversion,
    p.adjusted_conversion - n.adjusted_conversion AS adjusted_gap
FROM arms p, arms n
WHERE p.has_select_promotion AND NOT n.has_select_promotion;

-- Product category funnel at session level: sessions that viewed, carted and ordered the category.
-- Purchase and checkout events use a different category taxonomy and item_id format, so every
-- item takes the category its item_name most often has on view_item events.
CREATE OR REPLACE TABLE category_funnel AS
WITH item_category AS (
    SELECT item_name,
           CASE
               WHEN item_category IS NULL OR trim(item_category) = '' OR item_category = '(not set)' THEN 'Unknown'
               WHEN regexp_matches(item_category, 'Sale') THEN 'Sale'
               WHEN regexp_matches(item_category, 'Apparel|T-Shirts|Men''s|Women''s|Hats|Kids|Socks') THEN 'Apparel'
               WHEN regexp_matches(item_category, 'Drinkware') THEN 'Drinkware'
               WHEN regexp_matches(item_category, 'Bags') THEN 'Bags'
               WHEN regexp_matches(item_category, 'Stationery|Notebooks|Writing|Stickers') THEN 'Stationery'
               WHEN regexp_matches(item_category, 'Shop by Brand|Google|YouTube|Android') THEN 'Brand collections'
               WHEN regexp_matches(item_category, 'Small Goods|Lifestyle') THEN 'Lifestyle'
               ELSE 'Other'
           END AS category
    FROM items_flat
    WHERE event_name = 'view_item'
    GROUP BY item_name, item_category
    QUALIFY row_number() OVER (PARTITION BY item_name ORDER BY count(*) DESC, item_category) = 1
), i AS (
    SELECT i.user_pseudo_id || '-' || CAST(i.ga_session_id AS VARCHAR) AS session_key,
           i.event_name, i.event_id, coalesce(c.category, 'Unknown') AS category
    FROM items_flat i LEFT JOIN item_category c USING (item_name)
    WHERE i.event_name IN ('view_item', 'add_to_cart', 'purchase')
      AND i.event_date BETWEEN DATE '2020-11-26' AND DATE '2021-01-25'
), s AS (
    SELECT category,
           count(DISTINCT session_key) FILTER (WHERE event_name = 'view_item') AS view_sessions,
           count(DISTINCT session_key) FILTER (WHERE event_name = 'add_to_cart') AS cart_sessions,
           count(DISTINCT session_key) FILTER (WHERE event_name = 'purchase'
                                               AND event_id IN (SELECT event_id FROM fact_transactions)) AS order_sessions
    FROM i GROUP BY category
)
SELECT category, view_sessions, cart_sessions, order_sessions,
       cart_sessions / view_sessions AS view_to_cart,
       order_sessions / cart_sessions AS cart_to_order,
       order_sessions / view_sessions AS view_to_order
FROM s
ORDER BY view_sessions DESC;
