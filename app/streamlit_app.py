"""Funnel explorer and A/B test sample-size planner for the Google Merchandise Store sample."""
from pathlib import Path

import pandas as pd
import streamlit as st

from stats import n_per_arm, srm_check, weeks_needed

DATA = Path(__file__).parent / 'data'
STEPS = ['Session', 'View item', 'Add to cart', 'Begin checkout', 'Add payment info', 'Order']


@st.cache_data
def load(name):
    return pd.read_csv(DATA / f'{name}.csv')


st.set_page_config(page_title='Merch Store funnel', layout='wide')
kpis = load('kpis').iloc[0]
st.title('Google Merchandise Store: funnel and test planner')
st.caption(f"GA4 obfuscated sample, sessions {kpis.first_date} to {kpis.last_date} (the window where every funnel step is tracked). "
           'Channel is first-touch: how the user was first acquired.')

funnel_tab, planner_tab = st.tabs(['Funnel explorer', 'Sample-size planner'])

with funnel_tab:
    cols = st.columns(4)
    cols[0].metric('Sessions', f'{kpis.sessions:,.0f}')
    cols[1].metric('Orders', f'{kpis.orders:,.0f}')
    cols[2].metric('Session conversion', f'{kpis.session_conversion:.2%}')
    cols[3].metric('AOV', f'${kpis.aov:,.2f}')

    seg = load('funnel_by_segment')
    dimension = st.selectbox('Compare by', sorted(seg.dimension.unique()), index=sorted(seg.dimension.unique()).index('New vs returning'))
    view = seg[seg.dimension == dimension]
    chosen = st.multiselect('Segments', sorted(view.segment.unique()), default=sorted(view.segment.unique()))
    view = view[view.segment.isin(chosen)]
    if view.empty:
        st.info('Pick at least one segment.')
    else:
        st.subheader('Share of sessions reaching each step')
        share = view.pivot(index='step', columns='segment', values='share_of_sessions').reindex(STEPS)
        st.bar_chart(share, stack=False, y_label='share of sessions', horizontal=True)
        conv = view[view.step_order > 1].pivot(index='step', columns='segment', values='step_conversion').reindex(STEPS[1:])
        st.subheader('Conversion from the previous step')
        st.dataframe(conv.style.format('{:.1%}'), width='stretch')

    st.subheader('Revenue at stake: USD per 30 days from +1 point at one step')
    ras = load('revenue_at_stake').set_index('step')[['step_conversion', 'usd_low', 'usd_base', 'usd_high']]
    st.dataframe(ras.style.format({'step_conversion': '{:.1%}', 'usd_low': '${:,.0f}', 'usd_base': '${:,.0f}', 'usd_high': '${:,.0f}'}),
                 width='stretch')
    st.caption('Base: extra sessions order at today\'s downstream rate. Low: at half that rate. High: base method on December traffic.')

with planner_tab:
    exp = load('experiment').iloc[0]
    st.write(f"Default inputs: new users' first-session product-view rate ({exp.baseline_view_rate:.1%}) "
             f'and {exp.weekly_new_users:,.0f} new users a week, from non-holiday weeks in the sample.')
    c1, c2 = st.columns(2)
    baseline = c1.number_input('Baseline rate (%)', 0.1, 99.0, float(exp.baseline_view_rate * 100), step=0.1, format='%.2f') / 100
    mde = c1.number_input('Minimum detectable effect, relative (%)', 0.5, 100.0, 5.0, step=0.5) / 100
    weekly = c1.number_input('Eligible users per week', 100, 10_000_000, int(exp.weekly_new_users), step=500)
    alpha = c2.select_slider('Significance level (two-sided)', [0.01, 0.05, 0.10], value=0.05)
    power = c2.select_slider('Power', [0.7, 0.8, 0.9], value=0.8)
    try:
        n = n_per_arm(baseline, mde, alpha, power)
    except ValueError as err:
        st.error(str(err))
    else:
        weeks = weeks_needed(n, weekly)
        r1, r2, r3 = st.columns(3)
        r1.metric('Users per arm', f'{n:,}')
        r2.metric('Total users', f'{2 * n:,}')
        r3.metric('Full weeks (minimum 2)', weeks)
        st.caption(f'Detects a change from {baseline:.2%} to {baseline * (1 + mde):.2%} '
                   f'({baseline * mde * 100:.2f} points). Avoid weeks with Black Friday, Cyber Monday or Christmas.')
        feasible = [m for m in (0.02, 0.03, 0.05, 0.1, 0.2) if baseline * (1 + m) < 1]
        grid = pd.DataFrame({'relative MDE': [f'{m:.0%}' for m in feasible],
                             'users per arm': [n_per_arm(baseline, m, alpha, power) for m in feasible]})
        grid['weeks'] = [weeks_needed(x, weekly) for x in grid['users per arm']]
        st.dataframe(grid, hide_index=True, width='stretch')

    st.subheader('Sample ratio mismatch check')
    s1, s2 = st.columns(2)
    control = s1.number_input('Users in control', 0, 100_000_000, 10_000)
    treatment = s2.number_input('Users in treatment', 0, 100_000_000, 10_000)
    if control + treatment > 0:
        p_value, mismatch = srm_check([control, treatment])
        if mismatch:
            st.error(f'SRM detected (p = {p_value:.2g}). Fix assignment before reading results.')
        else:
            st.success(f'No SRM (p = {p_value:.3f}).')
