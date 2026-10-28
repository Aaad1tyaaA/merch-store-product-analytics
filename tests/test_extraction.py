"""Synthetic checks that do not require Google credentials or source data."""
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from download_bq import file_sha256, verified_existing, write_batches


def test_streaming_retains_duplicate_rows_nulls_and_source_types(tmp_path):
    schema = pa.schema([('user_pseudo_id', pa.string()), ('ga_session_id', pa.int64()),
                        ('purchase_revenue_usd', pa.float64())])
    first = pa.RecordBatch.from_pylist([
        {'user_pseudo_id': '<Other>', 'ga_session_id': None, 'purchase_revenue_usd': 0.0},
        {'user_pseudo_id': 'a', 'ga_session_id': 10, 'purchase_revenue_usd': 12.5}], schema=schema)
    second = pa.RecordBatch.from_pylist([
        {'user_pseudo_id': 'a', 'ga_session_id': 10, 'purchase_revenue_usd': 12.5}], schema=schema)
    path = tmp_path / 'events.parquet'
    assert write_batches(path, iter([first, second]), 3) == 3
    table = pq.read_table(path)
    assert table.schema == schema
    assert table.to_pylist() == first.to_pylist() + second.to_pylist()


def test_failed_or_short_stream_is_not_published_and_existing_files_are_preserved(tmp_path):
    path = tmp_path / 'events.parquet'
    batch = pa.record_batch({'value': [1, 2]})
    with pytest.raises(ValueError, match='Incomplete download'):
        write_batches(path, [batch], 3)
    assert not path.exists() and not path.with_suffix('.parquet.part').exists()
    write_batches(path, [batch], 2)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_batches(path, [batch], 2)
    assert path.read_bytes() == before


def test_resume_rejects_modified_data_and_changed_sql(tmp_path):
    path = tmp_path / 'events.parquet'
    write_batches(path, [pa.record_batch({'value': [1, 2]})], 2)
    receipt = {'rows': 2, 'sha256': file_sha256(path), 'sql_sha256': 'original-query'}
    assert verified_existing(path, receipt, 'original-query', 2)
    with pytest.raises(ValueError):
        verified_existing(path, receipt, 'changed-query', 2)
    write_path = tmp_path / 'different.parquet'
    write_batches(write_path, [pa.record_batch({'value': [1, 99]})], 2)
    path.write_bytes(write_path.read_bytes())
    with pytest.raises(ValueError):
        verified_existing(path, receipt, 'original-query', 2)


def test_event_and_item_queries_use_the_same_parent_identity():
    events = (ROOT / 'sql/bq_events_flat.sql').read_text()
    items = (ROOT / 'sql/bq_items_flat.sql').read_text()
    assert events.split('\nSELECT\n', 1)[0] == items.split('\nSELECT\n', 1)[0]
    assert 'WITH OFFSET AS item_offset' in items
    assert "event_name IN ('view_item'" not in items
    assert 'CROSS JOIN UNNEST(items)' not in events


def test_download_receipt_follows_verified_stream_and_rest_only(tmp_path, monkeypatch):
    import download_bq
    from types import SimpleNamespace
    monkeypatch.setattr(download_bq, 'ROOT', tmp_path)
    batch = pa.record_batch({'value': [1, 2]})

    class Rows:
        total_rows = 2

        def to_arrow_iterable(self, *, bqstorage_client):
            assert bqstorage_client is None
            return iter([batch])

    def result(*, page_size):
        assert page_size == 10000
        return Rows()

    job = SimpleNamespace(result=result, job_id='test-job', total_bytes_processed=1, cache_hit=False)
    entry = {'path': 'data/parquet/test.parquet', 'expected_rows': 2,
             'sql_sha256': 'test-sql', 'start': '20201101'}
    receipt = download_bq.download_file(job, entry)
    assert receipt['rows'] == 2 and receipt['job_id'] == 'test-job'
    assert receipt['sha256'] == file_sha256(tmp_path / entry['path'])
    entry['expected_rows'] = 3
    with pytest.raises(ValueError, match='BigQuery returned 2, expected 3'):
        download_bq.download_file(job, entry)


def test_missing_adc_stops_before_using_the_blocked_bundled_oauth_client(tmp_path, monkeypatch):
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError
    import pydata_google_auth
    import download_bq
    (tmp_path / 'sql').mkdir()
    (tmp_path / 'sql/bq_extraction_profile.sql').write_text('SELECT 1')
    monkeypatch.setattr(download_bq, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['download_bq.py', 'example-project'])

    def no_adc(*args, **kwargs):
        raise DefaultCredentialsError('No configured credentials')

    def no_interactive_fallback(*args, **kwargs):
        raise AssertionError('The blocked bundled OAuth client must not be started')

    monkeypatch.setattr(google.auth, 'default', no_adc)
    monkeypatch.setattr(pydata_google_auth, 'default', no_interactive_fallback)
    with pytest.raises(RuntimeError, match='Application Default Credentials'):
        download_bq.main()


def test_complete_receipts_allow_offline_resume_with_windows_sql_line_endings(tmp_path, monkeypatch, capsys):
    import hashlib
    import json
    import google.auth
    import download_bq
    monkeypatch.setattr(download_bq, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['download_bq.py', 'example-project'])
    (tmp_path / 'sql').mkdir()
    (tmp_path / 'docs/verification').mkdir(parents=True)
    sql = 'SELECT\n1;\n'
    digest = hashlib.sha256(sql.encode()).hexdigest()
    for name in ['extraction_profile', 'events_flat', 'items_flat']:
        (tmp_path / f'sql/bq_{name}.sql').write_text(sql, encoding='utf-8', newline='\r\n')
    rows = [{'source_month': start[:6], 'event_rows': 1, 'item_rows': 1,
             'property_dates': 1, 'invalid_property_dates': 0, 'events_with_repeated_selected_keys': 0}
            for start, _ in download_bq.MONTHS]
    download_bq.save_json(tmp_path / 'docs/verification/extraction_source_profile.json',
                          {'sql_sha256': digest, 'rows': rows})
    download_bq.save_json(tmp_path / 'docs/verification/source_coverage.json',
                          [{'event_count': 3, 'day_count': 3}])
    manifest = {'dataset': download_bq.DATASET, 'files': {}}
    for name in ['events_flat', 'items_flat']:
        for start, _ in download_bq.MONTHS:
            relative = f'data/parquet/{name}_{start[:6]}.parquet'
            path = tmp_path / relative
            write_batches(path, [pa.record_batch({'value': [1]})], 1)
            manifest['files'][relative] = {'rows': 1, 'sha256': file_sha256(path), 'sql_sha256': digest}
    download_bq.save_json(tmp_path / 'docs/source_manifest.json', manifest)

    def no_auth(*args, **kwargs):
        raise AssertionError('A complete verified source must not request credentials')

    monkeypatch.setattr(google.auth, 'default', no_auth)
    download_bq.main()
    assert 'no Google login or download needed' in capsys.readouterr().out
