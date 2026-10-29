"""Checks on the full database. Skipped when ga4.duckdb has not been built (for example in CI)."""
from pathlib import Path

import duckdb
import pytest

DB = Path(__file__).resolve().parents[1] / 'ga4.duckdb'
pytestmark = pytest.mark.skipif(not DB.exists(), reason='ga4.duckdb not built')


@pytest.fixture(scope='module')
def con():
    c = duckdb.connect(str(DB), read_only=True)
    c.execute("SET TimeZone='UTC'")
    yield c
    c.close()


def one(con, sql):
    return con.execute(sql).fetchone()[0]


def test_source_totals(con):
    assert one(con, 'SELECT COUNT(*) FROM events_flat') == 4_295_584
    assert one(con, 'SELECT COUNT(DISTINCT user_pseudo_id) FROM events_flat') == 270_154
    assert one(con, 'SELECT COUNT(DISTINCT event_date) FROM events_flat') == 92
    assert one(con, 'SELECT COUNT(DISTINCT event_name) FROM events_flat') == 17


def test_model_totals(con):
    assert one(con, 'SELECT COUNT(*) FROM fact_sessions') == 360_129
    assert one(con, 'SELECT COUNT(*) FROM fact_transactions') == 4_451
    assert one(con, 'SELECT COUNT(*) FROM dim_users') == 270_154


def test_keys_are_unique(con):
    assert one(con, 'SELECT COUNT(*) - COUNT(DISTINCT session_key) FROM fact_sessions') == 0
    assert one(con, 'SELECT COUNT(*) - COUNT(DISTINCT transaction_id) FROM fact_transactions') == 0
    assert one(con, 'SELECT COUNT(*) - COUNT(DISTINCT user_pseudo_id) FROM dim_users') == 0


def test_revenue_reconciles(con):
    tx = one(con, 'SELECT SUM(revenue_usd) FROM fact_transactions')
    assert tx == pytest.approx(307_640.0)
    assert one(con, 'SELECT SUM(revenue_usd) FROM fact_sessions') == pytest.approx(tx)
    assert one(con, 'SELECT SUM(revenue_usd) FROM dim_users') == pytest.approx(tx)


def test_funnels_never_grow(con):
    grows = one(con, """SELECT COUNT(*) FROM (
        SELECT sessions - lag(sessions) OVER (PARTITION BY dimension, segment ORDER BY step_order) AS d
        FROM (SELECT 'all' AS dimension, 'all' AS segment, step_order, sessions FROM funnel_overall
              UNION ALL SELECT dimension, segment, step_order, sessions FROM funnel_by_segment))
        WHERE d > 0""")
    assert grows == 0


def test_funnel_ends_at_session_conversion(con):
    orders_step = one(con, 'SELECT sessions FROM funnel_overall WHERE step_order = 6')
    assert orders_step == one(con, 'SELECT COUNT(*) FROM fact_sessions WHERE in_funnel_window AND has_order')


def test_model_contract_and_session_attributes(con):
    assert one(con, '''SELECT count(*) FROM fact_transactions t
        ANTI JOIN fact_sessions s USING (session_key)''') == 0
    assert one(con, '''SELECT count(*) FROM fact_sessions s
        ANTI JOIN dim_users u USING (user_pseudo_id)''') == 0
    assert one(con, '''SELECT count(*) FROM fact_events WHERE session_key IS NULL
        OR user_pseudo_id IS NULL OR ga_session_id IS NULL''') == 0
    assert one(con, '''SELECT count(*) FROM fact_sessions WHERE revenue_usd < 0
        OR orders < 0 OR channel NOT IN ('Organic Search', 'Paid Search', 'Direct', 'Referral', 'Unknown')''') == 0
    assert one(con, '''SELECT count(*) FROM (SELECT session_key FROM fact_events
        GROUP BY 1 HAVING count(DISTINCT device_category) > 1 OR count(DISTINCT country) > 1
        OR count(DISTINCT channel) > 1)''') == 0
