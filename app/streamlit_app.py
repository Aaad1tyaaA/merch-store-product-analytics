"""Product analytics workspace built from committed GA4 aggregate evidence."""
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import altair as alt

from stats import n_per_arm, srm_check, weeks_needed

DATA = Path(__file__).parent / 'data'
STEPS = ['Session', 'View item', 'Add to cart', 'Begin checkout', 'Add payment info', 'Order']


@st.cache_data
def load(name):
    return pd.read_csv(DATA / f'{name}.csv')


ACCENT = '#F29B62'
PALETTE = [ACCENT, '#75B8AA', '#A6A4D3', '#E6C76E', '#91ACCE', '#D992AE']


def chart(spec, description):
    st.altair_chart(spec.properties(height=290).configure_view(strokeWidth=0),
                    width='stretch', alt=description)


def takeaway(title, text):
    text = text.replace('$', r'\$')
    st.info(f'**{title}**  \n{text}')


st.set_page_config(page_title='Merch Store · Product Analytics', page_icon='📊', layout='wide')
st.markdown('''<style>
.block-container {max-width:1480px;padding-top:2.5rem}
[data-testid="stMetric"] {background:rgba(242,155,98,.055);border:1px solid rgba(242,155,98,.18);border-radius:14px;padding:18px}
[data-testid="stMetricLabel"] {color:#b7b8be}
h1 {letter-spacing:-.045em} h3 {letter-spacing:-.025em}
[data-testid="stTabs"] {margin-top:1.4rem}
[data-testid="stAlert"] {border-radius:12px;background:rgba(242,155,98,.08);border:1px solid rgba(242,155,98,.18)}
[data-testid="stAlert"] p {color:#E9EDF2}
</style>''', unsafe_allow_html=True)
kpis = load('kpis').iloc[0]
overall = load('funnel_overall')
opportunities = load('revenue_at_stake')
st.caption('ADITYA PATIL / PRODUCT ANALYTICS / GOOGLE MERCHANDISE STORE')
st.title('Where does the purchase journey break?')
st.caption(f"GA4 obfuscated sample, sessions {kpis.first_date} to {kpis.last_date} (the window where every funnel step is tracked). "
           'Historical sample data, not a live store. All monetary values are USD.')

cols = st.columns(4)
cols[0].metric('Sessions', f'{kpis.sessions:,.0f}')
cols[1].metric('Revenue', f'${kpis.revenue_usd:,.0f}')
cols[2].metric('Session conversion', f'{kpis.session_conversion:.2%}')
cols[3].metric('Average order value', f'${kpis.aov:,.2f}')

business_tab, funnel_tab, customers_tab, evidence_tab, planner_tab = st.tabs([
    'Business health', 'Funnel explorer', 'Customers & channels', 'Discovery & evidence', 'Sample-size planner'])

with business_tab:
    st.subheader('Fix discovery before polishing checkout.')
    view_step = overall.loc[overall.step == 'View item'].iloc[0]
    opportunity = opportunities.loc[opportunities.step == 'View item'].iloc[0]
    takeaway('The decision',
             f'{1 - view_step.share_of_sessions:.1%} of sessions never record a product view. '
             f'A +1 percentage-point gain at that step models ${opportunity.usd_base:,.0f} per 30 days '
             f'(${opportunity.usd_low:,.0f}–${opportunity.usd_high:,.0f} sensitivity range). '
             'Validate tracking first; then test a best-seller grid for new visitors.')
    weekly = load('weekly_north_star')
    weekly['week'] = pd.to_datetime(weekly.week)
    complete_week = weekly.week.dt.date.between(date.fromisoformat(kpis.first_date),
                                               date.fromisoformat(kpis.last_date) - timedelta(days=6))
    weekly = weekly[(weekly.days == 7) & complete_week]
    left, right = st.columns(2)
    with left:
        st.subheader('Weekly revenue')
        chart(alt.Chart(weekly).mark_area(color=ACCENT, opacity=.75, line={'color': ACCENT}).encode(
            x=alt.X('week:T', title='Week starting', axis=alt.Axis(format='%d %b', tickCount=6)), y=alt.Y('revenue_usd:Q', title='Revenue (USD)', axis=alt.Axis(format='$,.0f')),
            tooltip=[alt.Tooltip('week:T', title='Week'), alt.Tooltip('revenue_usd:Q', format='$,.0f', title='Revenue')]),
            'Weekly revenue across complete weeks inside the reliable funnel window.')
    with right:
        st.subheader('Weekly purchasing users')
        chart(alt.Chart(weekly).mark_line(color='#75B8AA', point=alt.OverlayMarkDef(color='#75B8AA', filled=True), strokeWidth=3).encode(
            x=alt.X('week:T', title='Week starting', axis=alt.Axis(format='%d %b', tickCount=6)), y=alt.Y('purchasing_users:Q', title='Purchasing users'),
            tooltip=['week:T', alt.Tooltip('purchasing_users:Q', format=',')]),
            'Distinct purchasing users each week, the project north-star metric.')
    peak = weekly.loc[weekly.revenue_usd.idxmax()]
    takeaway('Read the seasonal pattern', f"The week of {peak.week:%d %b %Y} leads these complete weeks with "
             f"${peak.revenue_usd:,.0f} revenue and {peak.purchasing_users:,.0f} purchasing users. "
             'Holiday demand is a reason to use a holdout and avoid holiday weeks in the discovery experiment.')
    st.caption('Complete Monday–Sunday weeks within 26 Nov–25 Jan only. These weekly totals cover a subset of the KPI window.')
    left, right = st.columns(2)
    with left:
        st.subheader('The session funnel')
        bars = alt.Chart(overall).encode(y=alt.Y('step:N', sort=STEPS, title=None),
            x=alt.X('sessions:Q', title='Sessions reaching step'),
            tooltip=['step:N', alt.Tooltip('sessions:Q', format=','), alt.Tooltip('share_of_sessions:Q', format='.1%')])
        chart(bars.mark_bar(color=ACCENT, cornerRadiusEnd=4), 'Session reach falls from 248,669 sessions to 3,196 sessions with an order.')
        st.caption(f'{kpis.orders:,.0f} distinct orders across {overall.iloc[-1].sessions:,.0f} purchasing sessions. Orders and purchasing sessions have different grains.')
    with right:
        st.subheader('Which step is worth testing?')
        base = alt.Chart(opportunities).encode(y=alt.Y('step:N', sort=STEPS[1:], title=None))
        ranges = base.mark_rule(color='#75B8AA', strokeWidth=3).encode(
            x=alt.X('usd_low:Q', title='Modelled USD per 30 days', axis=alt.Axis(format='$,.0f')), x2='usd_high:Q')
        points = base.mark_point(color=ACCENT, filled=True, size=100).encode(x='usd_base:Q',
            tooltip=['step:N', alt.Tooltip('usd_base:Q', format='$,.0f', title='Base'),
                     alt.Tooltip('usd_low:Q', format='$,.0f', title='Low'), alt.Tooltip('usd_high:Q', format='$,.0f', title='High')])
        chart(ranges + points, 'Revenue sensitivity ranges with a base-case dot for a one-point gain at each funnel step.')
        st.caption('Dot = base scenario; line = low/high assumptions, not confidence intervals. This is an opportunity model, not achieved revenue.')


with funnel_tab:
    st.subheader('Find the leak. Compare who experiences it.')
    seg = load('funnel_by_segment')
    dimension = st.selectbox('Compare by', sorted(seg.dimension.unique()), index=sorted(seg.dimension.unique()).index('New vs returning'))
    view = seg[seg.dimension == dimension]
    chosen = st.multiselect('Segments', sorted(view.segment.unique()), default=sorted(view.segment.unique()))
    view = view[view.segment.isin(chosen)]
    if view.empty:
        st.info('Pick at least one segment.')
    else:
        st.subheader('Share of sessions reaching each step')
        chart(alt.Chart(view).mark_bar(cornerRadiusEnd=3).encode(
            y=alt.Y('step:N', sort=STEPS, title=None), yOffset='segment:N',
            x=alt.X('share_of_sessions:Q', title='Share of sessions', axis=alt.Axis(format='.0%')),
            color=alt.Color('segment:N', scale=alt.Scale(range=PALETTE), title='Segment'),
            tooltip=['segment:N', 'step:N', alt.Tooltip('sessions:Q', format=','), alt.Tooltip('share_of_sessions:Q', format='.1%')]),
            f'Funnel reach by {dimension} for the selected segments.')
        order_rates = view[view.step == 'Order']
        best = order_rates.loc[order_rates.share_of_sessions.idxmax()]
        takeaway('Selected segment readout', f"{best.segment} has the highest observed session conversion among "
                 f"the selected groups ({best.share_of_sessions:.2%}). This comparison is descriptive; "
                 'group mix and tracking can explain gaps. It does not establish a causal effect.')
        conv = view[view.step_order > 1]
        st.subheader('Conversion from the previous step')
        chart(alt.Chart(conv).mark_rect().encode(
            x=alt.X('step:N', sort=STEPS[1:], title=None, axis=alt.Axis(labelAngle=-20)),
            y=alt.Y('segment:N', title=None), color=alt.Color('step_conversion:Q', scale=alt.Scale(scheme='tealblues'),
            legend=alt.Legend(format='.0%'), title='Conversion'),
            tooltip=['segment:N', 'step:N', alt.Tooltip('step_conversion:Q', format='.1%')]),
            'Heatmap of conversion from the previous step for each selected segment.')
        with st.expander('Inspect or download this segment data'):
            st.dataframe(view, hide_index=True, width='stretch')
            st.download_button('Download selected segments', view.to_csv(index=False), 'funnel-segments.csv', 'text/csv')

    st.subheader('Revenue at stake: USD per 30 days from +1 point at one step')
    ras = load('revenue_at_stake').set_index('step')[['step_conversion', 'usd_low', 'usd_base', 'usd_high']]
    with st.expander('Inspect revenue scenario assumptions'):
        st.dataframe(ras.style.format({'step_conversion': '{:.1%}', 'usd_low': '${:,.0f}', 'usd_base': '${:,.0f}', 'usd_high': '${:,.0f}'}), width='stretch')
    st.caption('Base: extra sessions order at today\'s downstream rate. Low: at half that rate. High: base method on December traffic.')

with customers_tab:
    st.subheader('Acquisition volume is only half the story.')
    channels = load('channel_quality')
    mix = channels.melt(id_vars='channel', value_vars=['share_of_users', 'share_of_revenue'], var_name='measure', value_name='share')
    mix['measure'] = mix.measure.map({'share_of_users': 'New users', 'share_of_revenue': '56-day revenue'})
    left, right = st.columns(2)
    with left:
        st.subheader('First-touch channel mix')
        chart(alt.Chart(mix).mark_bar(cornerRadiusEnd=3).encode(
            y=alt.Y('channel:N', sort=channels.channel.tolist(), title=None), yOffset='measure:N',
            x=alt.X('share:Q', axis=alt.Axis(format='.0%'), title='Share'),
            color=alt.Color('measure:N', scale=alt.Scale(range=PALETTE[:2]), title=None),
            tooltip=['channel:N', 'measure:N', alt.Tooltip('share:Q', format='.1%')]), 'Share of acquired users versus their 56-day revenue by first-touch channel.')
    with right:
        st.subheader('Revenue per acquired user')
        chart(alt.Chart(channels).mark_bar(color='#75B8AA', cornerRadiusEnd=3).encode(
            y=alt.Y('channel:N', sort='-x', title=None),
            x=alt.X('revenue_per_user_56d:Q', title='56-day revenue per user (USD)', axis=alt.Axis(format='$,.2f')),
            tooltip=['channel:N', alt.Tooltip('users:Q', format=','), alt.Tooltip('buyer_rate_56d:Q', format='.1%'),
                     alt.Tooltip('revenue_per_user_56d:Q', format='$,.2f')]), 'Revenue per acquired user, measured over equal 56-day follow-up windows.')
    paid = channels.loc[channels.channel == 'Paid Search'].iloc[0]
    takeaway('Review paid targeting before scaling', f"Paid Search brings {paid.share_of_users:.1%} of new users but "
             f"{paid.share_of_revenue:.1%} of their 56-day revenue. Check acquisition quality and targeting. "
             'Without media spend, this is not a ROAS or profitability estimate.')
    st.caption('First-touch attribution. New users first seen 12–30 Nov 2020, each followed for 56 days. Unknown remains visible as its own channel.')
    st.subheader('Do new users return?')
    retention = load('retention_cohorts')
    retention = retention[retention.week_number.between(1, 8)].copy()
    chart(alt.Chart(retention).mark_rect().encode(
        x=alt.X('week_number:O', title='Weeks since first observed session'),
        y=alt.Y('cohort_week:O', title='Cohort week'),
        color=alt.Color('retention:Q', scale=alt.Scale(scheme='tealblues'), legend=alt.Legend(format='.0%'), title='Retention'),
        tooltip=['cohort_week:O', 'week_number:O', alt.Tooltip('cohort_users:Q', format=','), alt.Tooltip('retention:Q', format='.1%')]),
        'Weekly cohort retention for weeks one through eight. Unavailable cells are blank.')
    st.caption('A return means any session, not a repeat order. Week 0 is omitted. Missing cells are not filled with zero; late cohorts have less follow-up. First and last calendar weeks can be partial.')
    left, right = st.columns(2)
    with left:
        st.subheader('Which categories turn views into carts?')
        categories = load('category_funnel')
        chart(alt.Chart(categories).mark_bar(color=ACCENT, cornerRadiusEnd=3).encode(
            y=alt.Y('category:N', sort='-x', title=None),
            x=alt.X('view_to_cart:Q', title='Cart sessions / view sessions', axis=alt.Axis(format='.0%')),
            tooltip=['category:N', alt.Tooltip('view_sessions:Q', format=','), alt.Tooltip('view_to_cart:Q', format='.1%')]),
            'Ratio of category cart sessions to category viewing sessions.')
        st.caption('Categories overlap across sessions. These event-reach ratios do not require a strict view-then-cart sequence.')
    with right:
        st.subheader('An activation signal worth monitoring')
        validation = load('activation_validation').iloc[0]
        odds = load('activation_odds')
        cart = odds.loc[odds.term == 'Added to cart in first session'].iloc[0]
        st.metric('Adjusted cart → later-purchase odds ratio', f'{cart.odds_ratio:.2f}×')
        takeaway('Predictive, not causal', f"First-session cart activity has an adjusted odds ratio of {cart.odds_ratio:.2f} "
                 f"(95% interval {cart.ci_low:.2f}–{cart.ci_high:.2f}) for a later purchase. "
                 f"The full model's out-of-time AUC is {validation.auc:.2f}. This does not prove that prompting carts creates purchases.")
        st.caption('New users first seen 26 Nov–26 Dec, excluding first-session buyers. Purchase outcome: 30 days. Odds ratios are not probability multipliers.')

with evidence_tab:
    st.subheader('A missing event can look like a missing customer.')
    takeaway('Validate the measurement before the experiment',
             'Some product-titled pages have low view_item coverage, and some sessions have no page_view. '
             'The discovery gap is a hypothesis to investigate—not proof that visitors failed to find a product.')
    left, right = st.columns(2)
    with left:
        st.subheader('Where sessions start')
        landing = pd.read_csv(DATA.parent.parent / 'docs/evidence/landing_pages.csv').nlargest(7, 'sessions')
        landing['page'] = landing.landing_page.str.replace(' / Google Merchandise Store', '', regex=False)
        chart(alt.Chart(landing).mark_bar(color=ACCENT, cornerRadiusEnd=3).encode(
            y=alt.Y('page:N', sort='-x', title=None, axis=alt.Axis(labelLimit=180)),
            x=alt.X('sessions:Q', title='Sessions'),
            tooltip=['landing_page:N', alt.Tooltip('sessions:Q', format=','), alt.Tooltip('product_view_rate:Q', format='.1%')]),
            'Seven most common first observed page titles with session volume and product-view rate.')
        st.caption('First recorded page title, not a confirmed landing URL. Titles can be shared across URLs.')
    with right:
        st.subheader('India versus the United States')
        markets = load('market_comparison').copy()
        markets[['gap', 'gap_ci_low', 'gap_ci_high']] *= 100
        base = alt.Chart(markets).encode(y=alt.Y('step:N', sort=STEPS[1:], title=None))
        intervals = base.mark_rule(color='#75B8AA', strokeWidth=3).encode(
            x=alt.X('gap_ci_low:Q', title='India − US conversion (percentage points)'), x2='gap_ci_high:Q')
        dots = base.mark_point(color=ACCENT, size=80, filled=True).encode(x='gap:Q',
            tooltip=['step:N', alt.Tooltip('gap:Q', format='.2f'), alt.Tooltip('gap_ci_low:Q', format='.2f'), alt.Tooltip('gap_ci_high:Q', format='.2f')])
        zero = alt.Chart(pd.DataFrame({'zero': [0]})).mark_rule(strokeDash=[4, 4], color='#B8BDC6').encode(x='zero:Q')
        chart(intervals + dots + zero, 'India-minus-US step conversion differences with user-clustered 95 percent intervals and a zero reference.')
        st.caption('All 95% difference intervals include zero. No clear difference does not establish equivalence.')
    st.subheader('When is event tracking reliable?')
    tracking = pd.read_csv(DATA.parent.parent / 'docs/evidence/tracking_daily.csv')
    chart(alt.Chart(tracking).mark_line(color='#75B8AA', strokeWidth=2).encode(
        x=alt.X('event_date:T', title='Date'),
        y=alt.Y('valid_purchase_share:Q', title='Purchases with valid transaction IDs', axis=alt.Axis(format='.0%')),
        tooltip=['event_date:T', alt.Tooltip('valid_purchase_share:Q', format='.1%'), 'purchase_events:Q']),
        'Daily share of purchase events carrying valid transaction IDs across the full source period.')
    st.caption('Reliable funnel window: 26 Nov–25 Jan. Cart tracking is incomplete earlier; transaction-ID coverage falls after 25 Jan. This is a retrospective audit, not live monitoring.')
    st.subheader('How uncertain is the revenue opportunity?')
    bootstrap = pd.read_csv(DATA.parent.parent / 'docs/evidence/revenue_bootstrap.csv')
    base = alt.Chart(bootstrap).encode(y=alt.Y('step:N', sort=STEPS[1:], title=None))
    chart(base.mark_rule(color='#75B8AA', strokeWidth=3).encode(
        x=alt.X('ci_low:Q', title='Modelled USD per 30 days', axis=alt.Axis(format='$,.0f')), x2='ci_high:Q') +
        base.mark_point(color=ACCENT, filled=True, size=80).encode(x='usd_base:Q', tooltip=['step:N',
        alt.Tooltip('usd_base:Q', format='$,.0f'), alt.Tooltip('ci_low:Q', format='$,.0f'), alt.Tooltip('ci_high:Q', format='$,.0f')]),
        'User-clustered bootstrap intervals around modelled revenue opportunity at each funnel step.')
    st.caption('1,000 whole-user bootstrap draws. These 95% intervals quantify sampling uncertainty conditional on a +1-point model. They do not quantify achievable intervention lift; low/base/high sensitivity cases are separate.')
    st.link_button('Read the complete evidence and definitions ↗', 'https://github.com/Aaad1tyaaA/merch-store-product-analytics/blob/main/docs/evidence_review.md')

with planner_tab:
    st.subheader('Turn the hypothesis into a decision-ready test.')
    takeaway('Proposed experiment', 'After validating product-view events, randomize eligible new visitors to a best-seller grid or the current experience. '
             'Primary outcome: first-session product-view rate. Monitor session conversion, revenue per session, and AOV as guardrails. '
             'The default plan needs 29,259 users per arm and three full weeks; this test has not been run.')
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
