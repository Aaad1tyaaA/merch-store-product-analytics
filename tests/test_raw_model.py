"""Synthetic source-reconciliation and missing-metadata regressions."""
from datetime import date, datetime, timezone
from pathlib import Path
import sys

import duckdb
import pyarrow as pa
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from setup_db import placeholder_profile, verify_tables


@pytest.fixture
def raw_source():
    stamp = datetime(2020, 11, 1, tzinfo=timezone.utc)
    common = {'event_date': date(2020, 11, 1), 'event_date_raw': '20201101',
              'source_table_suffix': '20201101', 'event_ts': stamp,
              'event_timestamp_micros': int(stamp.timestamp() * 1000000)}
    rows = [
        {**common, 'event_id': 'e1', 'user_pseudo_id': 'a', 'event_name': 'view_item', 'n_items': 1, 'purchase_revenue_usd': None},
        {**common, 'event_id': 'e2', 'user_pseudo_id': 'a', 'event_name': 'view_item', 'n_items': 1, 'purchase_revenue_usd': None},
        {**common, 'event_id': 'e3', 'user_pseudo_id': None, 'event_name': 'purchase', 'n_items': 1, 'purchase_revenue_usd': 12.5},
        {**common, 'event_id': 'e4', 'user_pseudo_id': '<Other>', 'event_name': 'purchase', 'n_items': 0, 'purchase_revenue_usd': 0.0},
    ]
    item_rows = [{'event_id': key, 'item_offset': 0, 'item_name': '', 'source_table_suffix': '20201101'}
                 for key in ['e1', 'e2', 'e3']]
    with duckdb.connect() as con:
        con.register('event_input', pa.Table.from_pylist(rows))
        con.register('item_input', pa.Table.from_pylist(item_rows))
        con.execute('CREATE TABLE events_flat AS SELECT * FROM event_input')
        con.execute('CREATE TABLE items_flat AS SELECT * FROM item_input')
        baseline = {'event_count': '4', 'distinct_user_ids_raw': '2', 'day_count': '1', 'event_type_count': '2'}
        profile = [{'source_month': '202011', 'event_rows': 4, 'item_rows': 3,
                    'purchase_events': 2, 'raw_purchase_revenue_usd': 12.5}]
        yield con, baseline, profile


def test_raw_reconciliation_retains_null_and_placeholder_users(raw_source):
    con, baseline, profile = raw_source
    assert all(check['passed'] for check in verify_tables(con, baseline, profile))
    coverage = next(r for r in placeholder_profile(con)
                    if r['table'] == 'events_flat' and r['column'] == 'user_pseudo_id')
    assert coverage['null'] == 1 and coverage['other'] == 1 and coverage['rows'] == 4


def test_orphan_items_are_detected(raw_source):
    con, baseline, profile = raw_source
    con.execute("UPDATE items_flat SET event_id = 'missing' WHERE event_id = 'e3'")
    with pytest.raises(ValueError, match='items_have_parent_events'):
        verify_tables(con, baseline, profile)


def test_timestamp_shift_is_not_silently_accepted(raw_source):
    con, baseline, profile = raw_source
    con.execute("UPDATE events_flat SET event_ts = event_ts + INTERVAL '1 hour' WHERE event_id = 'e1'")
    with pytest.raises(ValueError, match='utc_timestamp_preserved'):
        verify_tables(con, baseline, profile)
