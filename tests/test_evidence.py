"""Statistical regressions on small, transparent examples; no private data or cloud needed."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analysis import clustered_ratio
from evidence import tracking_alerts, revenue_bootstrap, landing_pages, activation_diagnostics


def test_clustered_ratio_preserves_rate_but_counts_repeated_users_together():
    y = np.repeat([0, 1, 0, 1], 10)
    n = np.ones(40)
    rate, clustered_se = clustered_ratio(y, n, np.repeat(['a', 'b', 'c', 'd'], 10))
    _, independent_se = clustered_ratio(y, n, np.arange(40))
    assert rate == .5
    assert clustered_se == pytest.approx(np.sqrt(1 / 12))
    assert clustered_se > independent_se * 3
    with pytest.raises(ValueError):
        clustered_ratio([1], [1], ['a'])


def test_tracking_alerts_find_outages_and_distinguish_persistent_zeros():
    days = pd.date_range('2020-11-01', periods=20)
    daily = pd.DataFrame({'cart': [0] * 5 + [100] * 5 + [1] + [100] * 9}, index=days)
    alerts = tracking_alerts(daily)
    assert set(days[:5]) <= set(alerts.date)
    isolated = alerts[alerts.date == days[10]].iloc[0]
    assert isolated.alert == 'low_volume' and isolated.ratio == pytest.approx(.01)
    assert alerts[alerts.date == days[0]].iloc[0].alert == 'zero_volume'
    assert days[8] not in set(alerts.date)


def test_tracking_coverage_finds_a_nonzero_outage_at_the_end():
    days = pd.date_range('2021-01-01', periods=31)
    daily = pd.DataFrame({'valid_purchase_share': [.95] * 25 + [.4, .22, .07, .11, .16, 0]}, index=days)
    alerts = tracking_alerts(daily)
    assert set(alerts.date) == set(days[25:])
    assert set(alerts.alert) == {'low_coverage'}


def test_revenue_bootstrap_is_paired_and_deterministic():
    class Result:
        def __init__(self, frame=None):
            self.frame = frame

        def df(self):
            return self.frame

        def fetchone(self):
            return (30,)

    class Connection:
        def sql(self, query):
            if 'DISTINCT session_date' in query:
                return Result()
            return Result(pd.DataFrame({'user': ['a', 'b', 'c', 'd'], 'n': [10]*4,
                'views': [5]*4, 'carts': [2]*4, 'checkouts': [2]*4,
                'payments': [1]*4, 'buyers': [1]*4, 'revenue': [100]*4}))

    result, paired = revenue_bootstrap(Connection(), repetitions=100)
    # Every user has identical ratios, so resampling whole users has zero variance.
    np.testing.assert_allclose(result.usd_base, [8, 10, 4, 8, 4])
    np.testing.assert_allclose(result.ci_low, result.ci_high)
    assert paired['bootstrap_share_view_exceeds_cart'] == 0


def test_landing_exit_use_page_views_and_preserve_unobserved_sessions():
    import duckdb
    with duckdb.connect() as con:
        con.execute("""CREATE TABLE fact_sessions AS SELECT * FROM (VALUES
            ('a-1', 'a', true, false, false, true),
            ('b-1', 'b', true, false, false, true),
            ('c-1', 'c', true, false, false, false)
            ) AS s(session_key, user_pseudo_id, is_new_session, has_view_item, has_order, in_funnel_window)""")
        con.execute("""CREATE TABLE events_flat AS SELECT user_pseudo_id, 1 AS ga_session_id,
            event_name, title AS page_title, CAST(stamp AS TIMESTAMP) AS event_ts, id AS event_id
            FROM (VALUES
            ('a', 'page_view', 'Exit', '2020-12-01 12:01:00', '2'),
            ('a', 'page_view', 'Home', '2020-12-01 12:00:00', '1'),
            ('a', 'user_engagement', 'Ignore', '2020-12-01 12:02:00', '3')
            ) AS e(user_pseudo_id, event_name, title, stamp, id)""")
        pages = landing_pages(con).set_index('session_key')
        assert set(pages.index) == {'a-1', 'b-1'}
        assert pages.loc['a-1', 'landing_page'] == 'Home'
        assert pages.loc['a-1', 'exit_page'] == 'Exit'
        assert pages.loc['b-1', 'landing_page'] == '[No page_view]'


def test_activation_diagnostics_uses_the_supplied_fit_without_refitting():
    scores = np.linspace(.01, .5, 20)
    d = pd.DataFrame({'train': [False]*20, 'y': [0]*15+[1]*5, 'activated': [0]*10+[1]*10})
    class FittedModel:
        def predict(self, frame):
            assert len(frame) == 20
            return scores

    calibration, summary = activation_diagnostics(d, FittedModel())
    assert calibration.users.sum() == 20
    assert summary['model_auc'] == 1
    assert summary['top_decile_precision'] == 1
    assert summary['top_decile_recall'] == pytest.approx(.4)
