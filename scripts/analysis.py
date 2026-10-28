"""Analysis functions used by the notebooks and by export_app_data.py, so both report the same numbers."""
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from stats import n_per_arm, proportion_ci, weeks_needed  # noqa: E402

HOLIDAYS = {'Black Friday': '2020-11-27', 'Cyber Monday': '2020-11-30', 'Christmas': '2020-12-25'}
TRAIN_END = '2020-12-10'  # activation cohort: train on first seen 26 Nov-10 Dec, test on 11-26 Dec


def connect(path=ROOT / 'ga4.duckdb'):
    con = duckdb.connect(str(path), read_only=True)
    con.execute("SET TimeZone='UTC'")
    return con


def market_comparison(con, a='India', b='United States'):
    """Step conversion with 95% margins of error for two markets."""
    f = con.sql(f"""SELECT segment, step_order, step, sessions,
                           lag(sessions) OVER (PARTITION BY segment ORDER BY step_order) AS entering
                    FROM funnel_by_segment
                    WHERE dimension = 'Market' AND segment IN ('{a}', '{b}')""").df()
    first = f[f.step_order == 1].set_index('segment').sessions
    overall = f[f.step_order == 6].assign(entering=lambda x: x.segment.map(first), step='Session conversion')
    rows = []
    for _, r in pd.concat([f[f.step_order > 1], overall]).iterrows():
        p, moe = proportion_ci(r.sessions, r.entering)
        rows.append({'step': r.step, 'step_order': r.step_order if r.step != 'Session conversion' else 7,
                     'market': r.segment, 'entering': int(r.entering), 'reached': int(r.sessions),
                     'rate': p, 'moe': moe})
    t = pd.DataFrame(rows).pivot(index=['step_order', 'step'], columns='market', values=['rate', 'moe', 'entering'])
    t.columns = [f'{m}_{v}' for v, m in t.columns]
    t = t.reset_index()
    overlap = ((t[f'{a}_rate'] - t[f'{a}_moe']) <= (t[f'{b}_rate'] + t[f'{b}_moe'])) & \
              ((t[f'{b}_rate'] - t[f'{b}_moe']) <= (t[f'{a}_rate'] + t[f'{a}_moe']))
    t['verdict'] = np.where(overlap, 'No clear difference', np.where(t[f'{a}_rate'] > t[f'{b}_rate'], f'{a} higher', f'{b} higher'))
    return t


def activation_frame(con):
    """New users in the activation cohort who did not order in their first session."""
    d = con.sql("""SELECT * FROM dim_users
                   WHERE is_new_user AND in_activation_cohort AND NOT first_session_ordered""").df()
    d['y'] = d.purchased_30d.astype(int)
    for col in ['activated', 'first_session_viewed_item', 'first_session_began_checkout']:
        d[col] = d[col].astype(int)
    d['log_engagement'] = np.log1p(d.first_session_engagement_sec)
    d['train'] = d.first_seen_date <= pd.Timestamp(TRAIN_END)
    return d


FORMULA = ("y ~ activated + first_session_viewed_item + first_session_began_checkout + log_engagement"
           " + C(first_session_device, Treatment('desktop'))"
           " + C(first_session_market, Treatment('United States'))"
           " + C(first_session_channel, Treatment('Direct'))")


def _label(term):
    for prefix in ["C(first_session_device, Treatment('desktop'))[T.", "C(first_session_market, Treatment('United States'))[T.",
                   "C(first_session_channel, Treatment('Direct'))[T."]:
        if term.startswith(prefix):
            kind = {'device': 'Device: ', 'market': 'Market: ', 'channel': 'First-touch channel: '}[prefix.split('_')[2].split(',')[0]]
            return kind + term[len(prefix):-1]
    return {'activated': 'Added to cart in first session', 'first_session_viewed_item': 'Viewed an item in first session',
            'first_session_began_checkout': 'Began checkout in first session',
            'log_engagement': 'log(1 + engagement seconds)', 'Intercept': 'Intercept'}[term]


def fit_activation(d):
    """Logistic regression on the training cohort; odds ratios and out-of-time validation."""
    model = smf.logit(FORMULA, d[d.train]).fit(disp=0)
    ci = np.exp(model.conf_int())
    odds = pd.DataFrame({'term': [_label(t) for t in model.params.index], 'odds_ratio': np.exp(model.params).values,
                         'ci_low': ci[0].values, 'ci_high': ci[1].values, 'p_value': model.pvalues.values})
    odds = odds[odds.term != 'Intercept'].reset_index(drop=True)
    test = d[~d.train].copy()
    test['score'] = model.predict(test)
    pos = (test.y == 1).to_numpy()
    ranks = rankdata(test.score)
    auc = (ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())
    top = test.score >= test.score.quantile(0.9)
    validation = {'train_users': int(d.train.sum()), 'train_buyers': int(d[d.train].y.sum()),
                  'test_users': len(test), 'test_buyers': int(pos.sum()), 'auc': auc,
                  'top_decile_rate': test[top].y.mean(), 'test_rate': test.y.mean(),
                  'top_decile_lift': test[top].y.mean() / test.y.mean(),
                  'top_decile_share_of_buyers': test[top].y.sum() / pos.sum()}
    return odds, validation


def experiment_target(con):
    """Top revenue-at-stake step and its weakest large segment (at least 5% of sessions)."""
    step = con.sql("SELECT step_order, step FROM revenue_at_stake WHERE rank_by_usd = 1").fetchone()
    seg = con.sql(f"""SELECT f.dimension, f.segment, f.step_conversion, s.share
                      FROM funnel_by_segment f
                      JOIN (SELECT dimension, segment, sessions / sum(sessions) OVER (PARTITION BY dimension) AS share
                            FROM funnel_by_segment WHERE step_order = 1) s USING (dimension, segment)
                      WHERE f.step_order = {step[0]} AND s.share >= 0.05
                      ORDER BY f.step_conversion LIMIT 1""").fetchone()
    return {'step_order': step[0], 'step': step[1], 'dimension': seg[0], 'segment': seg[1],
            'segment_rate': seg[2], 'segment_share': seg[3]}


def experiment_population(con):
    """New users first seen in full funnel-window weeks without Cyber Monday, Christmas or New Year:
    first-session product-view rate and weekly volume."""
    return con.sql("""SELECT date_trunc('week', first_seen_date) AS week, count(*) AS new_users,
                             avg(first_session_viewed_item::INT) AS view_rate,
                             avg(first_session_ordered::INT) AS order_rate
                      FROM dim_users
                      WHERE is_new_user AND (first_seen_date BETWEEN DATE '2020-12-07' AND DATE '2020-12-20'
                                             OR first_seen_date BETWEEN DATE '2021-01-04' AND DATE '2021-01-24')
                      GROUP BY 1 ORDER BY 1""").df()


def power_table(baseline, weekly_users, mdes=(0.02, 0.03, 0.05, 0.075, 0.10)):
    rows = []
    for m in mdes:
        n = n_per_arm(baseline, m)
        weeks = weeks_needed(n, weekly_users)
        rows.append({'relative_mde': m, 'absolute_mde_pts': baseline * m * 100, 'n_per_arm': n,
                     'weeks_needed': weeks, 'months_needed': round(weeks * 7 / 30.4, 1)})
    return pd.DataFrame(rows)


def cuped_estimate(con):
    """Variance reduction CUPED would give returning users: covariate = viewed an item in the
    4 pre-period weeks (14 Dec-10 Jan), outcome = viewed an item in a 2-week test window (11-24 Jan)."""
    d = con.sql("""WITH pre AS (
                       SELECT user_pseudo_id, max(has_view_item::INT) AS x FROM fact_sessions
                       WHERE session_date BETWEEN DATE '2020-12-14' AND DATE '2021-01-10' GROUP BY 1),
                   post AS (
                       SELECT user_pseudo_id, max(has_view_item::INT) AS y FROM fact_sessions
                       WHERE session_date BETWEEN DATE '2021-01-11' AND DATE '2021-01-24' GROUP BY 1)
                   SELECT x, y FROM post JOIN pre USING (user_pseudo_id)""").df()
    rho = d.x.corr(d.y)
    theta = d.x.cov(d.y) / d.x.var()
    adjusted = d.y - theta * (d.x - d.x.mean())
    return {'returning_users': len(d), 'outcome_rate': d.y.mean(), 'covariate_rate': d.x.mean(),
            'correlation': rho, 'theta': theta, 'variance_reduction': 1 - adjusted.var() / d.y.var()}


BLUE, ORANGE, GRAY, INK, MUTED = '#2a78d6', '#eb6834', '#b4b2a9', '#0b0b0b', '#52514e'


def chart_style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'figure.dpi': 110, 'savefig.dpi': 150, 'savefig.bbox': 'tight', 'figure.facecolor': '#fcfcfb',
        'axes.facecolor': '#fcfcfb', 'axes.edgecolor': GRAY, 'axes.labelcolor': MUTED, 'axes.titlecolor': INK,
        'axes.titlesize': 12, 'axes.titleweight': 'bold', 'axes.titlelocation': 'left',
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': False,
        'xtick.color': MUTED, 'ytick.color': MUTED, 'font.size': 10, 'text.color': INK,
    })
    (ROOT / 'charts').mkdir(exist_ok=True)
