"""Session, order and funnel rules on a small synthetic event log (no BigQuery needed)."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

ROOT = Path(__file__).resolve().parents[1]
DAY = datetime(2020, 12, 1, 10, tzinfo=timezone.utc)


def event(n, user, sid, name, minute=0, snum=1, **extra):
    ts = DAY + timedelta(minutes=minute)
    return {'event_id': f'e{n}', 'user_pseudo_id': user, 'ga_session_id': sid, 'ga_session_number': snum,
            'event_name': name, 'event_ts': ts, 'event_date': ts.date(), 'engagement_time_msec': 1000,
            'first_source': 'google', 'first_medium': 'organic', 'device_category': 'mobile',
            'country': 'India', 'transaction_id': None, 'purchase_revenue_usd': None,
            'total_item_quantity': None, **extra}


@pytest.fixture
def con():
    rows = [
        # user a: full funnel, purchase event duplicated
        event(1, 'a', 100, 'session_start'), event(2, 'a', 100, 'view_item', 1),
        event(3, 'a', 100, 'add_to_cart', 2), event(4, 'a', 100, 'begin_checkout', 3),
        event(5, 'a', 100, 'add_payment_info', 4),
        event(6, 'a', 100, 'purchase', 5, transaction_id='T1', purchase_revenue_usd=50.0),
        event(7, 'a', 100, 'purchase', 6, transaction_id='T1', purchase_revenue_usd=50.0),
        # user b shares ga_session_id 100 with user a: a different session
        event(8, 'b', 100, 'session_start', first_medium='cpc', device_category='desktop', country='United States'),
        event(9, 'b', 100, 'view_item', 1, first_medium='cpc', device_category='desktop', country='United States'),
        # user c: purchase with a placeholder id is not an order
        event(10, 'c', 200, 'session_start'),
        event(11, 'c', 200, 'purchase', 1, transaction_id='(not set)', purchase_revenue_usd=20.0),
        # user c returns and orders in a second session
        event(16, 'c', 300, 'view_item', 598, snum=2), event(17, 'c', 300, 'add_to_cart', 599, snum=2),
        event(12, 'c', 300, 'begin_checkout', 600, snum=2), event(13, 'c', 300, 'add_payment_info', 601, snum=2),
        event(14, 'c', 300, 'purchase', 602, snum=2, transaction_id='T2', purchase_revenue_usd=30.0),
        # session outside the funnel window
        event(15, 'd', 400, 'session_start', event_ts=datetime(2020, 11, 5, tzinfo=timezone.utc), event_date=date(2020, 11, 5)),
    ]
    items = [
        {'event_id': 'e2', 'user_pseudo_id': 'a', 'ga_session_id': 100, 'event_name': 'view_item',
         'item_name': 'Tee', 'item_category': 'Home/Apparel/', 'event_date': date(2020, 12, 1)},
        {'event_id': 'e3', 'user_pseudo_id': 'a', 'ga_session_id': 100, 'event_name': 'add_to_cart',
         'item_name': 'Tee', 'item_category': 'Home/Apparel/', 'event_date': date(2020, 12, 1)},
        {'event_id': 'e6', 'user_pseudo_id': 'a', 'ga_session_id': 100, 'event_name': 'purchase',
         'item_name': 'Tee', 'item_category': 'Apparel', 'event_date': date(2020, 12, 1)},
    ]
    c = duckdb.connect()
    c.register('e', pa.Table.from_pylist(rows))
    c.register('i', pa.Table.from_pylist(items))
    c.execute('CREATE TABLE events_flat AS SELECT * FROM e')
    c.execute('CREATE TABLE items_flat AS SELECT * FROM i')
    for script in ['sql/02_model.sql', 'sql/03_metrics.sql']:
        c.execute((ROOT / script).read_text(encoding='utf-8'))
    yield c
    c.close()


def one(con, sql):
    return con.execute(sql).fetchone()[0]


def test_session_key_includes_user(con):
    assert one(con, 'SELECT COUNT(*) FROM fact_sessions') == 5
    assert one(con, "SELECT COUNT(*) FROM fact_sessions WHERE ga_session_id = 100") == 2


def test_orders_are_deduplicated_and_placeholders_excluded(con):
    assert one(con, 'SELECT COUNT(*) FROM fact_transactions') == 2
    assert one(con, "SELECT COUNT(*) FROM fact_transactions WHERE transaction_id = '(not set)'") == 0
    assert one(con, 'SELECT SUM(revenue_usd) FROM fact_transactions') == 80.0


def test_revenue_reconciles_across_grains(con):
    tx = one(con, 'SELECT SUM(revenue_usd) FROM fact_transactions')
    assert one(con, 'SELECT SUM(revenue_usd) FROM fact_sessions') == tx
    assert one(con, 'SELECT SUM(revenue_usd) FROM dim_users') == tx


def test_funnel_never_grows_and_ends_at_orders(con):
    sessions = [r[0] for r in con.execute('SELECT sessions FROM funnel_overall ORDER BY step_order').fetchall()]
    assert sessions == [4, 3, 2, 2, 2, 2]
    assert sessions[-1] == one(con, 'SELECT COUNT(*) FROM fact_sessions WHERE has_order AND in_funnel_window')


def test_funnel_window_and_first_touch_channel(con):
    assert one(con, 'SELECT COUNT(*) FROM fact_sessions WHERE NOT in_funnel_window') == 1
    assert one(con, "SELECT channel FROM dim_users WHERE user_pseudo_id = 'b'") == 'Paid Search'
    assert one(con, "SELECT is_new_user FROM dim_users WHERE user_pseudo_id = 'c'") is True


def test_category_comes_from_view_taxonomy(con):
    assert one(con, "SELECT order_sessions FROM category_funnel WHERE category = 'Apparel'") == 1
