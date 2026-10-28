"""Build a self-contained raw DuckDB database and reconcile it with the source."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import hashlib

import duckdb

from download_bq import ROOT, MONTHS, file_sha256, save_json


def verify_tables(con, baseline, profile):
    checks = []

    def check(name, sql, expected):
        actual = con.execute(sql).fetchone()[0]
        passed = math.isclose(actual, expected, rel_tol=1e-10, abs_tol=.005) if isinstance(expected, float) else actual == expected
        checks.append({'name': name, 'passed': passed, 'actual': actual, 'expected': expected})
        if not passed:
            raise ValueError(f'{name}: expected {expected!r}, got {actual!r}')

    check('event_rows_match_source', 'SELECT COUNT(*) FROM events_flat', int(baseline['event_count']))
    check('raw_users_match_source', 'SELECT COUNT(DISTINCT user_pseudo_id) FROM events_flat', int(baseline['distinct_user_ids_raw']))
    check('property_dates_match_source', 'SELECT COUNT(DISTINCT event_date) FROM events_flat', int(baseline['day_count']))
    check('event_types_match_source', 'SELECT COUNT(DISTINCT event_name) FROM events_flat', int(baseline['event_type_count']))
    check('item_rows_match_source', 'SELECT COUNT(*) FROM items_flat', sum(int(r['item_rows']) for r in profile))
    check('event_id_unique', '''SELECT COUNT(*) FROM
        (SELECT event_id FROM events_flat GROUP BY event_id HAVING COUNT(*) <> 1)''', 0)
    check('item_occurrence_unique', '''SELECT COUNT(*) FROM
        (SELECT event_id, item_offset FROM items_flat GROUP BY ALL HAVING COUNT(*) <> 1)''', 0)
    check('no_null_event_keys', 'SELECT COUNT(*) FROM events_flat WHERE event_id IS NULL', 0)
    check('items_have_parent_events', '''SELECT COUNT(*) FROM items_flat i
        ANTI JOIN events_flat e ON i.event_id = e.event_id''', 0)
    check('item_counts_match_each_parent', '''WITH item_counts AS (
        SELECT event_id, COUNT(*) AS n FROM items_flat GROUP BY event_id)
        SELECT COUNT(*) FROM events_flat e LEFT JOIN item_counts i USING (event_id)
        WHERE COALESCE(e.n_items, 0) <> COALESCE(i.n, 0)''', 0)
    check('utc_timestamp_preserved', '''SELECT COUNT(*) FROM events_flat
        WHERE epoch_us(event_ts) IS DISTINCT FROM event_timestamp_micros''', 0)
    check('property_date_preserved', '''SELECT COUNT(*) FROM events_flat
        WHERE strftime(event_date, '%Y%m%d') IS DISTINCT FROM event_date_raw''', 0)
    check('purchase_events_match_source', "SELECT COUNT(*) FROM events_flat WHERE event_name = 'purchase'",
          sum(int(r['purchase_events']) for r in profile))
    check('raw_purchase_revenue_matches_source', "SELECT SUM(purchase_revenue_usd) FROM events_flat WHERE event_name = 'purchase'",
          sum(float(r['raw_purchase_revenue_usd']) for r in profile))
    for r in profile:
        for table, field in [('events_flat', 'event_rows'), ('items_flat', 'item_rows')]:
            check(f"{table}_{r['source_month']}_rows", f"SELECT COUNT(*) FROM {table} WHERE substr(source_table_suffix, 1, 6) = '{r['source_month']}'", int(r[field]))
    return checks


def placeholder_profile(con):
    result = []
    for table in ['events_flat', 'items_flat']:
        columns = [name for name, dtype, *_ in con.execute(f'DESCRIBE {table}').fetchall() if dtype == 'VARCHAR']
        for name in columns:
            column = '"' + name.replace('"', '""') + '"'
            row = con.execute(f'''SELECT COUNT(*), COUNT(*) FILTER (WHERE {column} IS NULL),
                COUNT(*) FILTER (WHERE {column} = ''),
                COUNT(*) FILTER (WHERE {column} = '<Other>'),
                COUNT(*) FILTER (WHERE {column} = '(data deleted)'),
                COUNT(*) FILTER (WHERE {column} = '(not set)'),
                COUNT(*) FILTER (WHERE {column} <> '' AND trim({column}) = '')
                FROM {table}''').fetchone()
            result.append(dict(zip(['table', 'column', 'rows', 'null', 'blank', 'other',
                                    'data_deleted', 'not_set', 'whitespace_only'], [table, name, *row])))
    return result


def build_model(path):
    """Rebuild the analytical tables from the verified raw tables."""
    with duckdb.connect(str(path)) as con:
        con.execute("SET memory_limit='4GB'")
        for script in ['sql/02_model.sql', 'sql/03_metrics.sql']:
            con.execute((ROOT / script).read_text(encoding='utf-8'))
        con.execute('CHECKPOINT')
    print('Built the session model and reporting tables.', flush=True)


def main():
    manifest_path = ROOT / 'docs/source_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    expected = {f'data/parquet/{name}_{start[:6]}.parquet'
                for name in ['events_flat', 'items_flat'] for start, _ in MONTHS}
    assert set(manifest['files']) == expected, 'Expected exactly six source files'
    for relative, receipt in manifest['files'].items():
        assert file_sha256(ROOT / relative) == receipt['sha256'], f'Modified source: {relative}'
        name = 'events_flat' if Path(relative).name.startswith('events_flat_') else 'items_flat'
        query = (ROOT / f'sql/bq_{name}.sql').read_text(encoding='utf-8')
        assert hashlib.sha256(query.encode()).hexdigest() == receipt['sql_sha256'], f'Changed extraction query: {name}'
    baseline = json.loads((ROOT / 'docs/verification/source_coverage.json').read_text())[0]
    profile = json.loads((ROOT / 'docs/verification/extraction_source_profile.json').read_text())['rows']
    digest = file_sha256(manifest_path)
    final = ROOT / 'ga4.duckdb'
    staging = ROOT / 'ga4.build.duckdb'
    if final.exists():
        with duckdb.connect(str(final), read_only=True) as con:
            con.execute("SET memory_limit='512MB'")
            con.execute('SET threads=1')
            temp = (ROOT / 'data/tmp').as_posix().replace("'", "''")
            con.execute(f"SET temp_directory='{temp}'")
            assert con.execute('SELECT manifest_sha256 FROM extraction_metadata').fetchone()[0] == digest, 'Existing database uses a different manifest; preserved'
            checks = verify_tables(con, baseline, profile)
        print(f'Existing database verified: {len(checks)} source checks passed.', flush=True)
        build_model(final)
        return
    if staging.exists():
        raise FileExistsError(f'Incomplete database preserved for inspection: {staging}')
    with duckdb.connect(str(staging)) as con:
        con.execute("SET memory_limit='512MB'")
        con.execute('SET threads=1')
        temp = (ROOT / 'data/tmp').as_posix().replace("'", "''")
        con.execute(f"SET temp_directory='{temp}'")
        for name in ['events_flat', 'items_flat']:
            files = [str(ROOT / relative) for relative in sorted(expected) if Path(relative).name.startswith(name)]
            con.execute(f'CREATE TABLE {name} AS SELECT * FROM read_parquet(?)', [files])
            print(f'Materialized {name}', flush=True)
        con.execute('CREATE TABLE extraction_metadata(manifest_sha256 VARCHAR)')
        con.execute('INSERT INTO extraction_metadata VALUES (?)', [digest])
        checks = verify_tables(con, baseline, profile)
        placeholders = placeholder_profile(con)
        con.execute('CHECKPOINT')
    with duckdb.connect(str(staging), read_only=True) as saved:
        assert saved.execute('SELECT COUNT(*) FROM events_flat').fetchone()[0] == int(baseline['event_count'])
        assert saved.execute('SELECT COUNT(*) FROM items_flat').fetchone()[0] == sum(int(r['item_rows']) for r in profile)
    staging.rename(final)
    save_json(ROOT / 'docs/verification/placeholder_profile.json', placeholders)
    save_json(ROOT / 'docs/verification/extraction_verification.json', {
        'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'database': final.name,
        'database_sha256': file_sha256(final), 'source_manifest_sha256': digest, 'checks': checks,
        'scope': 'Raw events and item occurrences only; no session filtering or order deduplication applied.'})
    print(f'{len(checks)} source checks passed. Saved {final.name}.', flush=True)
    build_model(final)


if __name__ == '__main__':
    main()
