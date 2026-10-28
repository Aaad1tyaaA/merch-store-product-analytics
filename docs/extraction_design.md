# Source extraction

The source is `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`, restricted to daily table suffixes from `20201101` through `20210131`. The saved BigQuery preflight observes 4,295,584 event rows and 3,982,732 item occurrences. These are extraction controls, not session or order totals.

## Grains and identity

`events_flat` retains one row per source event occurrence. `items_flat` retains one row per element of the source `items` array, across every event type with items. Restricting the item table to view, cart and purchase events would lose promotion and other item-bearing events.

There is no assumed native unique event ID. The extraction key combines the source table suffix, a SHA-256 fingerprint of the complete source record and an ordinal within identical source records. Exact duplicate source rows are retained. Their ordinals are interchangeable because their complete source payloads are identical; the key is an extraction surrogate, not a Google-issued identifier. Both queries use the same parent-key construction before items are unnested. `item_offset` preserves the original position in the item array. Validation must establish unique event keys, unique event-plus-offset item keys and complete parent coverage.

## Dates and parameters

`event_timestamp_micros` and the UTC `event_ts` preserve source event time. `event_date_raw` and its parsed `event_date` preserve the property's reporting date independently. UTC dates are not substituted for property dates.

Scalar extraction is allowed only after checking that the selected parameter keys occur at most once within each event. The live source preflight found no repeated occurrences of `ga_session_id`, `ga_session_number`, `engagement_time_msec` or `page_title`, and no invalid property dates. Missing session IDs do not cause raw events to be dropped. Unexpected string-valued session parameters are retained separately for inspection.

First-touch source, medium and campaign remain labelled as first-touch fields. They do not establish the source of the current visit. Event-level promotion names are retained as a JSON string containing distinct source labels, rather than selecting an arbitrary item label.

## Download and verification

Monthly GoogleSQL queries use bound string parameters and US processing location. Every extraction query is dry-run first and has a 10 GiB processing cap. The downloader runs read-only GoogleSQL through the ordinary query-results API rather than the billable Storage API. Google blocked the default PyData Authentication OAuth client in this account, so authentication uses Google Cloud CLI Application Default Credentials, loaded through `pydata-google-auth`. The official CLI requires Cloud Platform OAuth scope, which permits more than this project's reads; that permission was explicitly approved before authorization. The local credential file stays outside the repository; the downloader does not create another credential cache.

The supported login command is `gcloud auth application-default login --disable-quota-project`. This does not enable billing. The download command is `python scripts/run_all.py <project-id>`. Once all six files pass their receipts, rebuilding locally does not require another download or Google login.

Up to six monthly files stream concurrently into compressed Parquet batches, with one REST iterator per file and 10,000 requested rows per page. Actual page sizes can be smaller under the API response limits. Query job references are saved before downloads so an interrupted run can reuse an unexpired result. Only the coordinator writes the completed-file manifest, preventing concurrent receipt updates from overwriting one another. A file is published only after its written row count matches BigQuery and the source-month control. An existing file is reused only when its count, SHA-256 digest and extraction-query digest match its receipt. Incomplete files never count as completed downloads.

The DuckDB build materializes the six Parquet inputs into self-contained raw tables. Verification reconciles total and monthly counts, raw pseudonymous user IDs, source dates, raw purchase-event revenue, timestamp fidelity and item-parent relationships. Placeholder profiles count NULL, empty strings, `<Other>`, `(data deleted)`, `(not set)` and whitespace-only strings without replacing or removing them. Session definitions and transaction deduplication belong to the later analytical model.
