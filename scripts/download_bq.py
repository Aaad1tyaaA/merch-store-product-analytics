"""Stream the three source months into verified local Parquet files."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATASET = 'bigquery-public-data.ga4_obfuscated_sample_ecommerce'
MONTHS = [('20201101', '20201130'), ('20201201', '20201231'), ('20210101', '20210131')]
MAX_BYTES_PER_QUERY = 10 * 1024**3


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def verified_existing(path, receipt, sql_sha256, expected_rows):
    if not path.exists():
        return False
    if (not receipt or receipt.get('sql_sha256') != sql_sha256
            or receipt.get('rows') != expected_rows
            or receipt.get('sha256') != file_sha256(path)
            or pq.ParquetFile(path).metadata.num_rows != expected_rows):
        raise ValueError(f'Existing file failed verification; preserved for inspection: {path}')
    return True


def write_batches(path, batches, expected_rows):
    partial = path.with_suffix(path.suffix + '.part')
    if path.exists() or partial.exists():
        raise FileExistsError(f'Refusing to overwrite {path} or its incomplete file')
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    count = 0
    next_progress = 100000
    try:
        for batch in batches:
            if writer is None:
                writer = pq.ParquetWriter(partial, batch.schema, compression='zstd')
            writer.write_batch(batch)
            count += batch.num_rows
            if count >= next_progress:
                print(f'  {path.name}: {count:,}/{expected_rows:,} rows', flush=True)
                next_progress = (count // 100000 + 1) * 100000
        if writer is None:
            raise ValueError('No Arrow batch or schema was returned')
        writer.close()
        writer = None
        if count != expected_rows or pq.ParquetFile(partial).metadata.num_rows != expected_rows:
            raise ValueError(f'Incomplete download: expected {expected_rows:,}, received {count:,}')
        partial.rename(path)
    except Exception:
        if writer is not None:
            writer.close()
        partial.unlink(missing_ok=True)
        raise
    return count


def download_file(job, entry):
    rows = job.result(page_size=10000)
    expected = entry['expected_rows']
    if rows.total_rows != expected:
        raise ValueError(f"{entry['path']}: BigQuery returned {rows.total_rows}, expected {expected}")
    if expected:
        batches = rows.to_arrow_iterable(bqstorage_client=None)
    else:
        table = rows.to_arrow(create_bqstorage_client=False)
        empty = pa.RecordBatch.from_arrays([pa.array([], type=f.type) for f in table.schema], schema=table.schema)
        batches = [empty]
    path = ROOT / entry['path']
    print(f'Downloading {path.name}: {expected:,} rows; job {job.job_id}', flush=True)
    write_batches(path, batches, expected)
    return {
        'rows': expected, 'sha256': file_sha256(path), 'bytes': path.stat().st_size,
        'sql_sha256': entry['sql_sha256'], 'job_id': job.job_id,
        'total_bytes_processed': job.total_bytes_processed, 'cache_hit': job.cache_hit,
        'source_month': entry['start'][:6], 'schema': str(pq.ParquetFile(path).schema_arrow),
        'downloaded_at_utc': datetime.now(timezone.utc).isoformat()}


def query_config(start=None, end=None, dry_run=False):
    from google.cloud import bigquery
    config = bigquery.QueryJobConfig(
        use_legacy_sql=False, dry_run=dry_run, maximum_bytes_billed=MAX_BYTES_PER_QUERY)
    if start is not None:
        config.query_parameters = [bigquery.ScalarQueryParameter('start', 'STRING', start),
                                   bigquery.ScalarQueryParameter('end', 'STRING', end)]
    return config


def load_profile(client):
    sql = (ROOT / 'sql/bq_extraction_profile.sql').read_text(encoding='utf-8')
    digest = hashlib.sha256(sql.encode()).hexdigest()
    path = ROOT / 'docs/verification/extraction_source_profile.json'
    profile = json.loads(path.read_text()) if path.exists() else None
    if profile is None or profile.get('sql_sha256') != digest:
        from google.cloud import bigquery
        job = client.query(sql, job_config=query_config(), location='US',
                           api_method=bigquery.enums.QueryApiMethod.QUERY)
        profile = {'sql_sha256': digest, 'job_id': job.job_id, 'location': 'US',
                   'rows': [dict(row) for row in job.result()]}
        save_json(path, profile)
    rows = profile['rows']
    baseline = json.loads((ROOT / 'docs/verification/source_coverage.json').read_text())[0]
    assert {r['source_month'] for r in rows} == {start[:6] for start, _ in MONTHS}
    assert sum(int(r['event_rows']) for r in rows) == int(baseline['event_count'])
    assert sum(int(r['property_dates']) for r in rows) == int(baseline['day_count'])
    assert all(int(r['invalid_property_dates']) == 0 for r in rows), 'Invalid property dates require review'
    assert all(int(r['events_with_repeated_selected_keys']) == 0 for r in rows), 'Repeated parameter keys require an explicit extraction rule'
    return {r['source_month']: r for r in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_id', help='Sandbox project used to execute the public-data queries')
    args = parser.parse_args()
    manifest_path = ROOT / 'docs/source_manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'dataset': DATASET, 'execution_project': args.project_id, 'location': 'US', 'files': {}}
    assert manifest['dataset'] == DATASET
    profile_path = ROOT / 'docs/verification/extraction_source_profile.json'
    profile_sql = (ROOT / 'sql/bq_extraction_profile.sql').read_text(encoding='utf-8')
    if (manifest['files'] and profile_path.exists()
            and json.loads(profile_path.read_text()).get('sql_sha256') == hashlib.sha256(profile_sql.encode()).hexdigest()):
        profile = load_profile(None)
        complete = True
        for name in ['events_flat', 'items_flat']:
            sql = (ROOT / f'sql/bq_{name}.sql').read_text(encoding='utf-8')
            digest = hashlib.sha256(sql.encode()).hexdigest()
            for start, _ in MONTHS:
                relative = f'data/parquet/{name}_{start[:6]}.parquet'
                expected = int(profile[start[:6]]['event_rows' if name == 'events_flat' else 'item_rows'])
                complete &= verified_existing(ROOT / relative, manifest['files'].get(relative), digest, expected)
        if complete:
            print('All six existing source files verified; no Google login or download needed.', flush=True)
            return
    from google.cloud import bigquery
    import pydata_google_auth
    from pydata_google_auth import cache

    import google.auth
    from google.auth.exceptions import DefaultCredentialsError
    try:
        google.auth.default()
    except DefaultCredentialsError as exc:
        raise RuntimeError('Configure Google Application Default Credentials before downloading.') from exc
    # The library's bundled OAuth client is blocked; use Google CLI credentials instead.
    credentials, _ = pydata_google_auth.default(None, credentials_cache=cache.NOOP)
    client = bigquery.Client(project=args.project_id, credentials=credentials, location='US')
    profile = load_profile(client)
    plan = []
    for name in ['events_flat', 'items_flat']:
        sql = (ROOT / f'sql/bq_{name}.sql').read_text(encoding='utf-8')
        digest = hashlib.sha256(sql.encode()).hexdigest()
        for start, end in MONTHS:
            expected = int(profile[start[:6]]['event_rows' if name == 'events_flat' else 'item_rows'])
            relative = f'data/parquet/{name}_{start[:6]}.parquet'
            path = ROOT / relative
            if verified_existing(path, manifest['files'].get(relative), digest, expected):
                print(f'Verified existing {path.name}: {expected:,} rows', flush=True)
                continue
            dry = client.query(sql, job_config=query_config(start, end, dry_run=True), location='US',
                               api_method=bigquery.enums.QueryApiMethod.QUERY)
            if dry.total_bytes_processed > MAX_BYTES_PER_QUERY:
                raise ValueError(f'{path.name}: estimate exceeds the query cap')
            plan.append({'name': name, 'start': start, 'end': end, 'path': relative,
                         'expected_rows': expected, 'estimated_bytes_processed': dry.total_bytes_processed,
                         'sql_sha256': digest})
    save_json(ROOT / 'docs/verification/extraction_plan.json', plan)
    print(f'{len(plan)} downloads planned after dry-run validation.', flush=True)
    jobs_path = ROOT / 'docs/verification/extraction_jobs.json'
    jobs = json.loads(jobs_path.read_text()) if jobs_path.exists() else {}
    errors = []
    prepared = []
    for entry in plan:
        sql = (ROOT / f"sql/bq_{entry['name']}.sql").read_text(encoding='utf-8')
        previous = jobs.get(entry['path'])
        if previous and all(previous.get(k) == entry[k] for k in ['sql_sha256', 'start', 'end']):
            job = client.get_job(previous['job_id'], location='US')
        else:
            job = client.query(sql, job_config=query_config(entry['start'], entry['end']), location='US',
                               api_method=bigquery.enums.QueryApiMethod.QUERY)
            jobs[entry['path']] = {k: entry[k] for k in ['sql_sha256', 'start', 'end']}
            jobs[entry['path']]['job_id'] = job.job_id
            save_json(jobs_path, jobs)
        prepared.append((entry, job))
    # One bounded REST stream per monthly file; receipts are written by this thread only.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(download_file, job, entry): entry for entry, job in prepared}
        for future in as_completed(futures):
            entry = futures[future]
            try:
                manifest['files'][entry['path']] = future.result()
            except Exception as exc:
                errors.append(f"{entry['path']}: {exc}")
                print(f'Download failed: {errors[-1]}', flush=True)
            else:
                save_json(manifest_path, manifest)
                print(f"Verified {Path(entry['path']).name}: {entry['expected_rows']:,} rows", flush=True)
    if errors:
        raise RuntimeError('\n'.join(errors))


if __name__ == '__main__':
    main()
