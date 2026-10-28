"""Export small aggregate tables for the Streamlit app (app/data) and Power BI (dashboard/data)."""
from analysis import ROOT, connect, market_comparison, activation_frame, fit_activation, \
    experiment_target, experiment_population, power_table, cuped_estimate
import pandas as pd

TABLES = ['funnel_overall', 'funnel_by_segment', 'revenue_at_stake', 'weekly_north_star',
          'retention_cohorts', 'channel_quality', 'promo_effect', 'category_funnel']


def main():
    con = connect()
    out = {t: con.sql(f'SELECT * FROM {t}').df() for t in TABLES}
    out['kpis'] = con.sql("""SELECT COUNT(*) AS sessions, SUM(orders) AS orders, SUM(revenue_usd) AS revenue_usd,
                                    AVG(has_order::INT) AS session_conversion, SUM(revenue_usd) / SUM(orders) AS aov,
                                    SUM(revenue_usd) / COUNT(*) AS revenue_per_session,
                                    MIN(session_date) AS first_date, MAX(session_date) AS last_date
                             FROM fact_sessions WHERE in_funnel_window""").df()
    promo = out['promo_effect'].iloc[0]
    out['promo_comparison'] = pd.DataFrame([
        {'basis': basis, 'basis_order': i, 'group': group, 'conversion': promo[f'{key}_{basis.lower()}_conversion']}
        for i, basis in enumerate(['Raw', 'Adjusted']) for group, key in [('Clicked a promotion', 'promo'), ('Did not', 'other')]])
    out['market_comparison'] = market_comparison(con)
    odds, validation = fit_activation(activation_frame(con))
    out['activation_odds'] = odds
    out['activation_validation'] = pd.DataFrame([validation])
    pop = experiment_population(con)
    baseline, weekly = pop.view_rate.mean(), pop.new_users.mean()
    out['power_table'] = power_table(baseline, weekly)
    out['experiment'] = pd.DataFrame([{**experiment_target(con), 'baseline_view_rate': baseline,
                                       'weekly_new_users': weekly, **{f'cuped_{k}': v for k, v in cuped_estimate(con).items()}}])
    con.close()
    for folder in ['app/data', 'dashboard/data']:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
        for name, frame in out.items():
            frame.to_csv(ROOT / folder / f'{name}.csv', index=False, lineterminator='\n')
    print(f'Exported {len(out)} tables to app/data and dashboard/data.')


if __name__ == '__main__':
    main()
