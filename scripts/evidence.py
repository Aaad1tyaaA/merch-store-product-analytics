"""Read-only evidence checks for the discovery recommendation. No cloud access required."""
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from analysis import ROOT, connect, market_comparison, activation_frame, fit_activation
from scipy.stats import rankdata


def landing_pages(con):
    """First/last page_view within each modelled session, ordered by UTC time and event ID."""
    return con.sql("""WITH pages AS (
        SELECT e.user_pseudo_id || '-' || CAST(e.ga_session_id AS VARCHAR) AS session_key,
               coalesce(nullif(trim(e.page_title), ''), '[Missing title]') AS title,
               row_number() OVER (PARTITION BY e.user_pseudo_id, e.ga_session_id ORDER BY e.event_ts, e.event_id) AS first_rank,
               row_number() OVER (PARTITION BY e.user_pseudo_id, e.ga_session_id ORDER BY e.event_ts DESC, e.event_id DESC) AS last_rank
        FROM events_flat e WHERE event_name = 'page_view'
    ), first_last AS (
        SELECT session_key, max(title) FILTER (WHERE first_rank = 1) AS landing_page,
               max(title) FILTER (WHERE last_rank = 1) AS exit_page
        FROM pages GROUP BY 1)
    SELECT s.session_key, s.user_pseudo_id, s.is_new_session, s.has_view_item, s.has_order,
           coalesce(p.landing_page, '[No page_view]') AS landing_page,
           coalesce(p.exit_page, '[No page_view]') AS exit_page
    FROM fact_sessions s LEFT JOIN first_last p USING (session_key)
    WHERE s.in_funnel_window""").df()


def revenue_bootstrap(con, repetitions=1000, seed=42):
    """Paired nonparametric bootstrap: resample users with all their sessions intact."""
    if repetitions < 100:
        raise ValueError('Use at least 100 bootstrap repetitions')
    d = con.sql("""SELECT user_pseudo_id, count(*) AS n,
        sum(has_view_item::INT) AS views, sum(has_add_to_cart::INT) AS carts,
        sum(has_begin_checkout::INT) AS checkouts, sum(has_add_payment_info::INT) AS payments,
        sum(has_order::INT) AS buyers, sum(revenue_usd) AS revenue
        FROM fact_sessions WHERE in_funnel_window GROUP BY 1 ORDER BY 1""").df()
    values = d.iloc[:, 1:].to_numpy(dtype=float)
    days = con.sql('SELECT count(DISTINCT session_date) FROM fact_sessions WHERE in_funnel_window').fetchone()[0]

    def estimate(t):
        return t[:-2] / t[1:-1] * t[-1] * .01 * 30 / days

    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(repetitions):
        weights = rng.multinomial(len(d), np.full(len(d), 1 / len(d)))
        totals = (values * weights[:, None]).sum(axis=0)
        draws.append(estimate(totals))
    draws = np.asarray(draws)
    lo, hi = np.quantile(draws, [.025, .975], axis=0)
    result = pd.DataFrame({'step': ['View item', 'Add to cart', 'Begin checkout', 'Add payment info', 'Order'],
                           'usd_base': estimate(values.sum(axis=0)), 'ci_low': lo, 'ci_high': hi})
    gap = draws[:, 0] - draws[:, 1]
    comparison = {'repetitions': repetitions, 'seed': seed, 'users': len(d),
                  'view_minus_cart_ci_low': float(np.quantile(gap, .025)),
                  'view_minus_cart_ci_high': float(np.quantile(gap, .975)),
                  'bootstrap_share_view_exceeds_cart': float(np.mean(gap > 0)),
                  'scope': 'Sampling uncertainty conditional on the +1-point scenario; not causal uncertainty.'}
    return result, comparison


def proxy_revenue(con):
    """Adjusted association in first-session non-buyers; no post-exposure behaviour controls."""
    d = con.sql("""SELECT first_session_viewed_item::INT AS viewed, purchased_30d::INT AS bought,
        revenue_30d, first_session_device AS device, first_session_market AS market,
        first_session_channel AS channel, CAST(date_trunc('week', first_seen_date) AS VARCHAR) AS week
        FROM dim_users WHERE is_new_user AND in_activation_cohort AND NOT first_session_ordered""").df()
    raw = d.groupby('viewed').agg(users=('bought', 'size'), buyers=('bought', 'sum'),
                                purchase_rate=('bought', 'mean'), revenue_per_user=('revenue_30d', 'mean')).reset_index()
    rows = []
    for outcome in ['bought', 'revenue_30d']:
        # Linear adjustment makes the standardized difference and its robust interval explicit.
        model = smf.ols(f'{outcome} ~ viewed + C(device) + C(market) + C(channel) + C(week)', d).fit(cov_type='HC3')
        lo, hi = model.conf_int().loc['viewed']
        rows.append({'outcome': outcome, 'adjusted_difference': model.params['viewed'], 'ci_low': lo, 'ci_high': hi})
    estimates = pd.DataFrame(rows)
    baseline = d.viewed.mean()
    extra_views = len(d) * baseline * .05
    estimates['additional_viewers_at_5pct_lift'] = extra_views
    for source, target in [('adjusted_difference', 'projected_change'), ('ci_low', 'projected_ci_low'), ('ci_high', 'projected_ci_high')]:
        estimates[target] = estimates[source] * extra_views
    return raw, estimates


def tracking_alerts(daily, threshold=.2):
    """Retrospective alert: compare each day with its other six neighbours (three either side).

    This uses future days: it is an outage audit, not an online monitoring claim.
    """
    rows = []
    for name in daily.columns:
        series = daily[name].astype(float)
        cutoff = .8 if name.endswith('_share') else threshold
        neighbours = pd.concat([series.shift(k) for k in [-3, -2, -1, 1, 2, 3]], axis=1)
        baseline = neighbours.median(axis=1)
        if name.endswith('_share'):
            baseline[:] = series.median()
        for day in daily.index:
            observed, expected = series.loc[day], baseline.loc[day]
            if neighbours.loc[day].count() >= 3 and expected > 0 and observed < cutoff * expected:
                rows.append({'date': day, 'metric': name, 'observed': observed, 'neighbour_median': expected,
                             'ratio': observed / expected, 'alert': 'low_coverage' if name.endswith('_share') else 'low_volume'})
            elif observed == 0:
                rows.append({'date': day, 'metric': name, 'observed': observed, 'neighbour_median': expected,
                             'ratio': 0 if expected > 0 else np.nan, 'alert': 'zero_volume'})
    return pd.DataFrame(rows, columns=['date', 'metric', 'observed', 'neighbour_median', 'ratio', 'alert'])


def daily_tracking(con):
    return con.sql("""SELECT event_date,
        count(*) FILTER (WHERE event_name = 'add_to_cart') AS add_to_cart,
        count(*) FILTER (WHERE event_name = 'purchase' AND transaction_id IS NOT NULL
            AND trim(transaction_id) <> '' AND transaction_id NOT IN ('(not set)', '<Other>', '(data deleted)')
            AND purchase_revenue_usd > 0) AS valid_purchase_events,
        count(*) FILTER (WHERE event_name = 'purchase') AS purchase_events
        FROM events_flat GROUP BY 1 ORDER BY 1""").df().set_index('event_date').asfreq('D', fill_value=0)


def activation_diagnostics(d, model):
    """Evaluate the same fitted activation model used for odds ratios and validation."""
    test = d[~d.train].copy()
    test['score'] = model.predict(test)
    test['decile'] = pd.qcut(test.score.rank(method='first'), 10, labels=False) + 1
    calibration = test.groupby('decile').agg(users=('y', 'size'), buyers=('y', 'sum'),
                                           predicted=('score', 'mean'), actual=('y', 'mean')).reset_index()
    pos = test.y == 1
    def auc(score):
        return (rankdata(score)[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())
    summary = {'model_auc': float(auc(test.score)), 'cart_rule_auc': float(auc(test.activated)),
               'brier_score': float(np.mean((test.score-test.y)**2)),
               'top_decile_precision': float(test[test.decile == 10].y.mean()),
               'top_decile_recall': float(test[test.decile == 10].y.sum() / test.y.sum())}
    assert calibration.users.sum() == len(test) and test.score.between(0, 1).all()
    return calibration, summary


def definition_sensitivity(con):
    rows = []
    for label, window, require_start, alternate_order in [
        ('Baseline', "s.in_funnel_window", False, False),
        ('Require session_start', "s.in_funnel_window", True, False),
        ('Start 25 November', "s.session_date BETWEEN DATE '2020-11-25' AND DATE '2021-01-25'", False, False),
        ('Order key: user + transaction', "s.in_funnel_window", False, True),
    ]:
        order_source = """SELECT session_key, count(*) AS orders, sum(purchase_revenue_usd) AS revenue_usd FROM (
            SELECT * FROM fact_events WHERE event_name = 'purchase' AND purchase_revenue_usd > 0
            AND transaction_id IS NOT NULL AND trim(transaction_id) <> ''
            AND transaction_id NOT IN ('(not set)', '<Other>', '(data deleted)')
            QUALIFY row_number() OVER (PARTITION BY user_pseudo_id, transaction_id ORDER BY event_ts, event_id) = 1
            ) GROUP BY 1""" if alternate_order else 'SELECT session_key, orders, revenue_usd FROM fact_sessions'
        r = con.sql(f"""WITH orders AS ({order_source})
            SELECT count(*) AS sessions, sum(coalesce(o.orders, 0)) AS orders,
                   sum(coalesce(o.revenue_usd, 0)) AS revenue_usd,
                   avg((coalesce(o.orders, 0) > 0)::INT) AS session_conversion,
                   avg(has_view_item::INT) AS product_view_rate
            FROM fact_sessions s LEFT JOIN orders o USING (session_key)
            WHERE {window} {'AND s.has_session_start' if require_start else ''}""").df().iloc[0].to_dict()
        rows.append({'definition': label, **r})
    return pd.DataFrame(rows)


def write_review(out):
    landing = pd.read_csv(out / 'landing_pages.csv')
    exits = pd.read_csv(out / 'nonviewer_exit_pages.csv')
    ras = pd.read_csv(out / 'revenue_bootstrap.csv')
    proxy = pd.read_csv(out / 'proxy_adjusted.csv').set_index('outcome')
    comparison = json.loads((out / 'revenue_bootstrap.json').read_text())
    alerts = pd.read_csv(out / 'tracking_alerts.csv')
    diagnostic = json.loads((out / 'activation_diagnostics.json').read_text())
    def table(frame):
        return '| ' + ' | '.join(frame.columns) + ' |\n|' + '|'.join(['---'] * len(frame.columns)) + '|\n' + '\n'.join(
            '| ' + ' | '.join(str(v).replace('|', '/') for v in row) + ' |' for row in frame.itertuples(index=False, name=None))
    lead = ras.iloc[0]
    purchase, dollars = proxy.loc['bought'], proxy.loc['revenue_30d']
    text = f"""# Discovery evidence and verification

I reproduced this analysis locally with `python scripts/evidence.py`. The script reads the database without changing it and writes the CSV evidence linked below. Notebook 07 displays the same results and charts.

## Landing and exit pages

I use the first and last recorded `page_view` title in each funnel-window session, ordered by UTC timestamp and event ID. These are observed page titles, not URLs or confirmed acquisition landing pages. Titles can be shared across URLs; equal timestamps have no verified order. Sessions without a page view remain visible.

{table(landing.head(10).round(4))}

Among sessions without a product-view event, the most common last observed pages are:

{table(exits.head(8).round(4))}

I found product-titled landing pages without `view_item`, and sessions without any `page_view`. I therefore validate event coverage before interpreting every non-viewer as a discovery failure. The best-seller grid is a testable hypothesis; this analysis does not establish why people leave. I would validate homepage and category-page tracking first, then test a grid on eligible landing pages.

## Clustered market comparisons

I now calculate delta-method standard errors clustered by cookie ID, keeping every session from a cookie together. I test the India-minus-US difference against zero rather than comparing overlap between two separate confidence intervals. The data show no clear difference at any step; this does not establish equivalence. The full differences and intervals are in [market_comparison.csv](evidence/market_comparison.csv).

## Revenue scenario uncertainty

I resample {comparison['users']:,} whole users with replacement, using {comparison['repetitions']:,} paired bootstrap draws and seed {comparison['seed']}. Every user's sessions stay together; the observed 61-day calendar stays fixed.

{table(ras.round(2))}

The product-view scenario is ${lead.usd_base:,.0f} per 30 days, with a sampling interval of ${lead.ci_low:,.0f}–${lead.ci_high:,.0f}. Its paired difference from add to cart has a 95% interval of ${comparison['view_minus_cart_ci_low']:,.0f}–${comparison['view_minus_cart_ci_high']:,.0f}. Product view exceeds cart in {comparison['bootstrap_share_view_exceeds_cart']:.1%} of bootstrap draws. This is a resampling frequency, not a posterior probability.

These intervals describe sampling uncertainty **conditional on the +1-point model**. They do not quantify whether an intervention can produce that gain or whether marginal viewers behave like existing viewers. Low/base/high sensitivity cases remain separate from these sampling intervals. Under the model, dollar rankings are inversely proportional to step conversion by construction.

## Product views and later purchases

I compare new users first seen 26 November–26 December who did not buy in their first session. Outcomes are a purchase indicator and revenue within 30 days of the first session. I adjust for first-session device, market, first-touch channel and cohort week with linear models and HC3 robust standard errors. I avoid engagement/cart/checkout controls because these can follow product viewing.

The adjusted purchase-rate difference is {purchase.adjusted_difference:.2%} (95% interval {purchase.ci_low:.2%}–{purchase.ci_high:.2%}). The adjusted revenue difference is ${dollars.adjusted_difference:.2f} per person (${dollars.ci_low:.2f}–${dollars.ci_high:.2f}).

Applying a 5% relative view-rate lift to this **historical non-buyer cohort only** gives {purchase.additional_viewers_at_5pct_lift:,.1f} extra viewers. If the adjusted association transferred unchanged to those marginal viewers, that corresponds to {purchase.projected_change:.1f} additional purchasing users ({purchase.projected_ci_low:.1f}–{purchase.projected_ci_high:.1f}) and ${dollars.projected_change:,.0f} revenue (${dollars.projected_ci_low:,.0f}–${dollars.projected_ci_high:,.0f}). This is neither a monthly estimate nor an estimate for the full experiment population. The intervals are conditional on fixed exposure lift and model specification; they omit unmeasured confounding, exposure-model uncertainty and transportability. Only a randomized holdout can estimate causal revenue impact.

## Tracking audit

I flag zero-volume days and counts below 20% of the median of the six neighbouring days. I also flag valid-purchase coverage below 80% of its full-period median, which catches sustained low-but-nonzero ID coverage after 25 January. There are {len(alerts)} metric-day alerts; several metrics can flag the same date. The audit uses future days and a full-period reference: it is retrospective, not live monitoring. The count rule misses partial recovery on 16–19 and 25 November, so the 26 November funnel start also relies on daily event inspection rather than this audit alone. Alerts require inspection and never remove data automatically. Full results: [tracking_alerts.csv](evidence/tracking_alerts.csv).

## Activation diagnostics and sensitivity

On the out-of-time test set, the full activation model has AUC {diagnostic['model_auc']:.3f}, versus {diagnostic['cart_rule_auc']:.3f} for the cart-only rule. Top-decile precision is {diagnostic['top_decile_precision']:.2%}, recall {diagnostic['top_decile_recall']:.1%}, and Brier score {diagnostic['brier_score']:.5f}. [Calibration by decile](evidence/activation_calibration.csv) makes prediction quality inspectable; AUC alone does not establish calibration.

I also rerun control totals under alternative order keys, requiring `session_start`, and starting the funnel one day earlier: [definition_sensitivity.csv](evidence/definition_sensitivity.csv). These are separate scenarios, not new default definitions.
"""
    (ROOT / 'docs/evidence_review.md').write_text(text, encoding='utf-8', newline='\n')


def main():
    out = ROOT / 'docs/evidence'
    out.mkdir(exist_ok=True)
    with connect() as con:
        pages = landing_pages(con)
        landing = pages.groupby('landing_page').agg(sessions=('session_key', 'size'),
            product_view_rate=('has_view_item', 'mean'), order_session_rate=('has_order', 'mean'))
        landing['share_of_sessions'] = landing.sessions / len(pages)
        landing = landing.sort_values('sessions', ascending=False)
        exits = pages[~pages.has_view_item].groupby('exit_page').size().rename('sessions').to_frame()
        exits['share_of_nonview_sessions'] = exits.sessions / exits.sessions.sum()
        exits = exits.sort_values('sessions', ascending=False)
        landing.to_csv(out / 'landing_pages.csv')
        exits.to_csv(out / 'nonviewer_exit_pages.csv')
        market_comparison(con).to_csv(out / 'market_comparison.csv', index=False)
        ras, comparison = revenue_bootstrap(con)
        ras.to_csv(out / 'revenue_bootstrap.csv', index=False)
        (out / 'revenue_bootstrap.json').write_text(json.dumps(comparison, indent=2) + '\n')
        raw, adjusted = proxy_revenue(con)
        raw.to_csv(out / 'proxy_raw.csv', index=False)
        adjusted.to_csv(out / 'proxy_adjusted.csv', index=False)
        daily = daily_tracking(con)
        daily['valid_purchase_share'] = daily.valid_purchase_events / daily.purchase_events.replace(0, np.nan)
        daily.to_csv(out / 'tracking_daily.csv')
        alerts = tracking_alerts(daily)
        alerts.to_csv(out / 'tracking_alerts.csv', index=False)
        activation = activation_frame(con)
        _, _, model = fit_activation(activation)
        calibration, diagnostics = activation_diagnostics(activation, model)
        calibration.to_csv(out / 'activation_calibration.csv', index=False)
        (out / 'activation_diagnostics.json').write_text(json.dumps(diagnostics, indent=2) + '\n')
        definition_sensitivity(con).to_csv(out / 'definition_sensitivity.csv', index=False)
    write_review(out)
    print(f'Wrote discovery evidence to {out}; {len(pages):,} sessions; {len(alerts)} tracking alerts.')


if __name__ == '__main__':
    main()
