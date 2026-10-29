"""Generate the Power BI project (PBIP: PBIR report + TMDL model) in dashboard/ from dashboard/data/*.csv.

Measures are defined once here with a pandas equivalent, so tests can check every Power BI
number against the analysis without opening Power BI.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import uuid

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / 'dashboard'
DATA = DASH / 'data'
NAME = 'merch-store'
REPORT = DASH / f'{NAME}.Report'
MODEL = DASH / f'{NAME}.SemanticModel'
SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric'
INK, MUTED, BLUE, TEAL, PAPER = '#142D4E', '#596B80', '#2563EB', '#0C857A', '#F2F5F9'

TABLES = ['kpis', 'funnel_overall', 'funnel_by_segment', 'revenue_at_stake', 'activation_odds',
          'retention_cohorts', 'channel_quality', 'promo_comparison', 'power_table',
          'discovery_landing', 'discovery_exits', 'tracking_daily', 'revenue_bootstrap', 'definition_sensitivity']
DATE_COLUMNS = {'cohort_week', 'first_date', 'last_date', 'event_date'}
SORT_BY = {('funnel_overall', 'step'): 'step_order', ('funnel_by_segment', 'step'): 'step_order',
           ('revenue_at_stake', 'step'): 'step_order', ('promo_comparison', 'basis'): 'basis_order',
           ('revenue_bootstrap', 'step'): 'step_order'}
ROW_FILTER = {'retention_cohorts': 'each [week_number] >= 1 and [week_number] <= 8'}
PAGES = [('where-we-lose-buyers', '01  Overview'), ('who-buys-and-what-to-test', '02  Customers'),
         ('product-discovery', '03  Discovery'), ('evidence-and-tracking', '04  Evidence')]
WIDTH, HEIGHT = 1440, 1080


def step_sessions(t, step):
    f = t['funnel_overall']
    return f.loc[f.step_order == step, 'sessions'].sum()


# name: (table, DAX, format, pandas equivalent of the measure's total)
MEASURES = {
    'Total sessions': ('kpis', 'SUM(kpis[sessions])', '#,0', lambda t: t['kpis'].sessions.sum()),
    'Total orders': ('kpis', 'SUM(kpis[orders])', '#,0', lambda t: t['kpis'].orders.sum()),
    'Total revenue': ('kpis', 'SUM(kpis[revenue_usd])', '\\$#,0', lambda t: t['kpis'].revenue_usd.sum()),
    'Average order value': ('kpis', 'DIVIDE([Total revenue], [Total orders])', '\\$#,0.00', lambda t: t['kpis'].revenue_usd.sum() / t['kpis'].orders.sum()),
    'Session conversion': ('kpis',
        'DIVIDE(CALCULATE(SUM(funnel_overall[sessions]), funnel_overall[step_order] = 6), '
        'CALCULATE(SUM(funnel_overall[sessions]), funnel_overall[step_order] = 1))',
        '0.00%', lambda t: step_sessions(t, 6) / step_sessions(t, 1)),
    'Funnel sessions': ('funnel_overall', 'SUM(funnel_overall[sessions])', '#,0', lambda t: t['funnel_overall'].sessions.sum()),
    'Step conversion': ('funnel_by_segment', 'AVERAGE(funnel_by_segment[step_conversion])', '0.0%', None),
    'USD at stake (low)': ('revenue_at_stake', 'SUM(revenue_at_stake[usd_low])', '\\$#,0', lambda t: t['revenue_at_stake'].usd_low.sum()),
    'USD at stake (base)': ('revenue_at_stake', 'SUM(revenue_at_stake[usd_base])', '\\$#,0', lambda t: t['revenue_at_stake'].usd_base.sum()),
    'USD at stake (high)': ('revenue_at_stake', 'SUM(revenue_at_stake[usd_high])', '\\$#,0', lambda t: t['revenue_at_stake'].usd_high.sum()),
    'Odds ratio': ('activation_odds', 'AVERAGE(activation_odds[odds_ratio])', '0.00', None),
    'CI low': ('activation_odds', 'AVERAGE(activation_odds[ci_low])', '0.00', None),
    'CI high': ('activation_odds', 'AVERAGE(activation_odds[ci_high])', '0.00', None),
    'Retention rate': ('retention_cohorts', 'AVERAGE(retention_cohorts[retention])', '0.0%', None),
    'Share of users': ('channel_quality', 'SUM(channel_quality[share_of_users])', '0.0%', lambda t: t['channel_quality'].share_of_users.sum()),
    'Share of revenue': ('channel_quality', 'SUM(channel_quality[share_of_revenue])', '0.0%', lambda t: t['channel_quality'].share_of_revenue.sum()),
    'Promo conversion': ('promo_comparison', 'AVERAGE(promo_comparison[conversion])', '0.00%', None),
    'Users per arm': ('power_table', 'SUM(power_table[n_per_arm])', '#,0', None),
    'Weeks needed': ('power_table', 'SUM(power_table[weeks_needed])', '0', None),
}
MEASURES.update({
    'Landing sessions': ('discovery_landing', 'SUM(discovery_landing[sessions])', '#,0', lambda t: t['discovery_landing'].sessions.sum()),
    'Landing view rate': ('discovery_landing', 'AVERAGE(discovery_landing[product_view_rate])', '0.0%', None),
    'Landing order rate': ('discovery_landing', 'AVERAGE(discovery_landing[order_session_rate])', '0.00%', None),
    'Exit sessions': ('discovery_exits', 'SUM(discovery_exits[sessions])', '#,0', lambda t: t['discovery_exits'].sessions.sum()),
    'Daily cart events': ('tracking_daily', 'SUM(tracking_daily[add_to_cart])', '#,0', lambda t: t['tracking_daily'].add_to_cart.sum()),
    'Valid order ID coverage': ('tracking_daily', 'AVERAGE(tracking_daily[valid_purchase_share])', '0%', None),
    'Bootstrap estimate': ('revenue_bootstrap', 'SUM(revenue_bootstrap[usd_base])', '\\$#,0', None),
    'Bootstrap lower bound': ('revenue_bootstrap', 'SUM(revenue_bootstrap[ci_low])', '\\$#,0', None),
    'Bootstrap upper bound': ('revenue_bootstrap', 'SUM(revenue_bootstrap[ci_high])', '\\$#,0', None),
    'Sensitivity conversion': ('definition_sensitivity', 'AVERAGE(definition_sensitivity[session_conversion])', '0.00%', None),
    'Sensitivity view rate': ('definition_sensitivity', 'AVERAGE(definition_sensitivity[product_view_rate])', '0.0%', None),
    'Sensitivity orders': ('definition_sensitivity', 'SUM(definition_sensitivity[orders])', '#,0', None),
})


def load_tables(folder=DATA):
    return {t: pd.read_csv(folder / f'{t}.csv') for t in TABLES}


def guid(*parts):
    return str(uuid.UUID(hashlib.md5('|'.join(parts).encode()).hexdigest()))


def short_id(*parts):
    return hashlib.md5('|'.join(parts).encode()).hexdigest()[:20]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


# ---------------------------------------------------------------- semantic model (TMDL)

def column_type(table, name, dtype):
    if name in DATE_COLUMNS:
        return 'dateTime', 'type date'
    if pd.api.types.is_integer_dtype(dtype):
        return 'int64', 'Int64.Type'
    if pd.api.types.is_float_dtype(dtype):
        return 'double', 'type number'
    if pd.api.types.is_bool_dtype(dtype):
        return 'boolean', 'type logical'
    return 'string', 'type text'


def quote(name):
    return name if name.replace('_', '').isalnum() else f"'{name}'"


def table_tmdl(table, frame):
    lines = [f'table {table}', f'\tlineageTag: {guid(table)}', '']
    for measure, (owner, dax, fmt, _) in MEASURES.items():
        if owner == table:
            lines += [f'\tmeasure {quote(measure)} = {dax}', f'\t\tformatString: {fmt}',
                      f'\t\tlineageTag: {guid(table, measure)}', '']
    types = []
    for col, dtype in frame.dtypes.items():
        tmdl_type, m_type = column_type(table, col, dtype)
        types.append(f'{{"{col}", {m_type}}}')
        lines += [f'\tcolumn {col}', f'\t\tdataType: {tmdl_type}', f'\t\tlineageTag: {guid(table, col)}',
                  '\t\tsummarizeBy: none', f'\t\tsourceColumn: {col}']
        if (table, col) in SORT_BY:
            lines.append(f'\t\tsortByColumn: {SORT_BY[(table, col)]}')
        if (table, col) == ('power_table', 'relative_mde'):
            lines.append('\t\tformatString: 0.0%')
        if (table, col) == ('retention_cohorts', 'cohort_week'):
            lines.append('\t\tformatString: dd MMM yyyy')
        if (table, col) == ('tracking_daily', 'event_date'):
            lines.append('\t\tformatString: dd MMM')
        lines += ['', '\t\tannotation SummarizationSetBy = User', '']
    steps = [f'\t\t\t\t\tSource = Csv.Document(File.Contents(DataFolder & "\\{table}.csv"), '
             f'[Delimiter = ",", Columns = {len(frame.columns)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
             '\t\t\t\t\tHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),',
             f'\t\t\t\t\tTyped = Table.TransformColumnTypes(Headers, {{{", ".join(types)}}}, "en-US")']
    last = 'Typed'
    if table in ROW_FILTER:
        steps[-1] += ','
        steps.append(f'\t\t\t\t\tFiltered = Table.SelectRows(Typed, {ROW_FILTER[table]})')
        last = 'Filtered'
    lines += [f'\tpartition {table} = m', '\t\tmode: import', '\t\tsource =', '\t\t\t\tlet', *steps,
              '\t\t\t\tin', f'\t\t\t\t\t{last}', '', '\tannotation PBI_ResultType = Table', '']
    return '\n'.join(lines)


def build_model(tables):
    shutil.rmtree(MODEL, ignore_errors=True)
    write_json(MODEL / 'definition.pbism', {
        '$schema': f'{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json',
        'version': '4.1', 'settings': {}})
    write_text(MODEL / 'definition/database.tmdl', 'database\n\tcompatibilityLevel: 1601\n')
    refs = '\n'.join(f'ref table {t}' for t in tables)
    write_text(MODEL / 'definition/model.tmdl', f'''model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tdiscourageImplicitMeasures
\tsourceQueryCulture: en-US
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

annotation PBI_QueryOrder = {json.dumps(['DataFolder', *tables])}

annotation __PBI_TimeIntelligenceEnabled = 0

{refs}
''')
    write_text(MODEL / 'definition/expressions.tmdl', f'''/// Folder holding the exported CSVs: <repository>\\dashboard\\data
expression DataFolder = "" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]
\tlineageTag: {guid('DataFolder')}

\tannotation PBI_ResultType = Text
''')
    for table, frame in tables.items():
        write_text(MODEL / f'definition/tables/{table}.tmdl', table_tmdl(table, frame))


# ---------------------------------------------------------------- report (PBIR)

def lit(value):
    return {'expr': {'Literal': {'Value': value}}}


def field(table, prop, kind='Column'):
    return {kind: {'Expression': {'SourceRef': {'Entity': table}}, 'Property': prop}}


def proj(table, prop, kind='Column'):
    return {'field': field(table, prop, kind), 'queryRef': f'{table}.{prop}', 'nativeQueryRef': prop,
            'active': True}


def m(name):
    return proj(MEASURES[name][0], name, 'Measure')


def c(table, column):
    return proj(table, column)


def title(text):
    return {'title': [{'properties': {'show': lit('true'), 'text': lit("'" + text.replace("'", "''") + "'"),
            'fontSize': lit('16D'), 'fontColor': fill(INK), 'fontFamily': lit("'Segoe UI Semibold'")}}]}


def fill(color):
    return {'solid': {'color': lit(f"'{color}'")}}


def visual(page, key, kind, pos, roles=None, objects=None, heading=None, sort=None, descending=False):
    x, y, w, h = pos
    v = {'visualType': kind}
    if roles:
        v['query'] = {'queryState': {role: {'projections': items} for role, items in roles.items()}}
        if sort:
            v['query']['sortDefinition'] = {'sort': [{'field': sort, 'direction': 'Descending' if descending else 'Ascending'}], 'isDefaultSort': False}
    if objects:
        v['objects'] = objects
    if heading:
        v['visualContainerObjects'] = title(heading)
    if kind != 'textbox':
        v.setdefault('visualContainerObjects', {}).update({
            'background': [{'properties': {'show': lit('true'), 'color': fill('#FFFFFF'), 'transparency': lit('0D')}}],
            'border': [{'properties': {'show': lit('true'), 'color': fill('#DFE6EF'), 'radius': lit('8D')}}],
            'padding': [{'properties': {side: lit('12D') for side in ['top', 'bottom', 'left', 'right']}}],
        })
        description = heading or ('Audience conversion from the previous purchase step.' if key == 'segments' else None)
        if description:
            v['visualContainerObjects']['general'] = [{'properties': {'altText': lit("'" + description.replace("'", "''") + "'")}}]
    v['drillFilterOtherVisuals'] = True
    name = short_id(page, key)
    z = 1000 + len(key) * 10 + int(name[:3], 16) % 9
    return name, {'$schema': f'{SCHEMA}/item/report/definition/visualContainer/1.1.0/schema.json', 'name': name,
                  'position': {'x': x, 'y': y, 'z': z, 'height': h, 'width': w, 'tabOrder': z}, 'visual': v}


def textbox(page, key, pos, text, size='12pt', color=INK, bold=False, background=None):
    result = visual(page, key, 'textbox', pos, objects={'general': [{'properties': {'paragraphs': [
        {'textRuns': [{'value': text, 'textStyle': {'fontWeight': 'bold' if bold else 'normal',
          'fontSize': size, 'fontFamily': 'Segoe UI', 'color': color}}]}]}}]})
    result[1]['visual']['visualContainerObjects'] = {
        'background': [{'properties': {'show': lit('true'), 'color': fill(background or PAPER), 'transparency': lit('0D')}}],
        'padding': [{'properties': {side: lit('0D') for side in ['top', 'bottom', 'left', 'right']}}],
    }
    return result


def grid_style(matrix=False):
    style = {
        'columnHeaders': [{'properties': {'fontSize': lit('12D'), 'fontFamily': lit("'Segoe UI'"), 'fontColor': fill(INK),
            'backColor': fill('#EAF0F7'), 'autoSizeColumnWidth': lit('true'), 'columnAdjustment': lit("'growToFit'")}}],
        'values': [{'properties': {'fontSize': lit('12D'), 'fontFamily': lit("'Segoe UI'"), 'fontColorPrimary': fill(INK),
            'fontColorSecondary': fill(INK), 'backColorPrimary': fill('#FFFFFF'), 'backColorSecondary': fill('#F5F8FC')}}],
        'grid': [{'properties': {'rowPadding': lit('2D'), 'gridVertical': lit('false'), 'gridHorizontal': lit('false')}}],
    }
    if matrix:
        style['rowHeaders'] = [{'properties': {'fontSize': lit('12D'), 'fontFamily': lit("'Segoe UI'"), 'fontColor': fill(INK)}}]
        style['subTotals'] = [{'properties': {'rowSubtotals': lit('false'), 'columnSubtotals': lit('false')}}]
        style['rowTotal'] = [{'properties': {'show': lit('false')}}]
        style['columnTotal'] = [{'properties': {'show': lit('false')}}]
    else:
        style['total'] = [{'properties': {'totals': lit('false')}}]
    return style


def chart_style(precision=0, dense=False):
    labels = {'show': lit('true'), 'fontSize': lit('12D'), 'fontFamily': lit("'Segoe UI'"),
              'color': fill(INK), 'labelDisplayUnits': lit('1D'), 'labelPrecision': lit(f'{precision}D')}
    if dense:
        labels['labelDensity'] = lit('20D')
        labels.update(labelPosition=lit("'Above'"), enableBackground=lit('true'),
                      backgroundColor=fill('#FFFFFF'), backgroundTransparency=lit('0D'))
    else:
        labels['labelPosition'] = lit("'OutsideEnd'")
        labels['labelDensity'] = lit('100D')
    return {
        'labels': [{'properties': labels}],
        'legend': [{'properties': {'showTitle': lit('false'), 'fontSize': lit('12D'), 'fontFamily': lit("'Segoe UI'"), 'position': lit("'Top'")}}],
        'categoryAxis': [{'properties': {'showAxisTitle': lit('false'), 'fontSize': lit('12D'), 'fontFamily': lit("'Segoe UI'"), 'labelColor': fill(MUTED), 'maxMarginFactor': lit('45D')}}],
        'valueAxis': [{'properties': {'showAxisTitle': lit('false'), 'fontSize': lit('12D'), 'fontFamily': lit("'Segoe UI'"), 'labelColor': fill(MUTED), 'start': lit('0D')}}],
    }


def gradient(measure):
    table = MEASURES[measure][0]
    return {'values': [{'properties': {'backColor': {'solid': {'color': {'expr': {'FillRule': {
        'Input': field(table, measure, 'Measure'),
        'FillRule': {'linearGradient2': {
            'min': {'color': {'Literal': {'Value': "'#FFFFFF'"}}},
            'max': {'color': {'Literal': {'Value': "'#B8D4F4'"}}},
            'nullColoringStrategy': {'strategy': {'Literal': {'Value': "'asZero'"}}}}}}}}}}},
        'selector': {'data': [{'dataViewWildcard': {'matchingOption': 1}}], 'metadata': f'{table}.{measure}'}}]}


def caption(projection, label):
    return {**projection, 'displayName': label}


def navigation(page, target, label, index):
    active = page == target
    name, result = visual(page, 'nav-' + target, 'actionButton', (18, 194 + index * 62, 172, 48))
    result['visual']['objects'] = {
        'text': [{'properties': {'show': lit('true')}},
                 {'properties': {'text': lit(f"'{label}'"), 'fontSize': lit('12D'),
                     'fontColor': fill('#FFFFFF' if active else '#D8E3F2'), 'bold': lit('true'),
                     'horizontalAlignment': lit("'center'")}, 'selector': {'id': 'default'}}],
        'icon': [{'properties': {'show': lit('false')}},
                 {'properties': {'shapeType': lit("'blank'"), 'placement': lit("'left'")}, 'selector': {'id': 'default'}}],
        'fill': [{'properties': {'show': lit('true')}},
                 {'properties': {'fillColor': fill(TEAL if active else '#193454')}, 'selector': {'id': 'default'}},
                 {'properties': {'fillColor': fill('#246B82')}, 'selector': {'id': 'hover'}}],
        'outline': [{'properties': {'show': lit('false')}}],
        'shape': [{'properties': {'tileShape': lit("'rectangleRounded'"), 'roundEdge': lit('8L')}},
                  {'properties': {'tileShape': lit("'rectangleRounded'")}, 'selector': {'id': 'default'}}],
    }
    result['visual']['visualContainerObjects'] = {
        'background': [{'properties': {'show': lit('false')}}], 'border': [{'properties': {'show': lit('false')}}],
        'visualLink': [{'properties': {'show': lit('true'), 'type': lit("'PageNavigation'"),
                        'navigationSection': lit(f"'{target}'"), 'tooltip': lit(f"'Open {label[4:]}'")}}],
    }
    result['howCreated'] = 'InsertVisualButton'
    return name, result


def chrome(page, heading, subtitle):
    backdrop = textbox(page, 'sidebar', (0, 0, 208, HEIGHT), '', background=INK)
    backdrop[1]['position']['z'] = 0
    return [backdrop,
        textbox(page, 'brand', (20, 24, 168, 54), 'MERCH', '28pt', '#FFFFFF', True, INK),
        textbox(page, 'brand-subtitle', (20, 78, 168, 44), 'PRODUCT ANALYTICS', '12pt', '#8FDDD0', True, INK),
        textbox(page, 'nav-label', (20, 150, 168, 30), 'EXPLORE THE STORY', '12pt', '#A4B6CB', True, INK),
        *[navigation(page, target, label, i) for i, (target, label) in enumerate(PAGES)],
        textbox(page, 'side-note', (20, 556, 168, 146), 'THE NEXT MOVE\n\nValidate tracking.\nTest discovery.', '12pt', '#FFFFFF', True, INK),
        textbox(page, 'side-source', (20, HEIGHT-176, 168, 148), 'GOOGLE MERCHANDISE STORE\n\nHistorical GA4 sample\nNov 2020 - Jan 2021', '12pt', '#A4B6CB', False, INK),
        textbox(page, 'title', (232, 24, 1184, 66), heading, '28pt', INK, True),
        textbox(page, 'subtitle', (232, 94, 1184, 30), subtitle, '12pt', MUTED),
    ]


def footer(page, text):
    return textbox(page, 'footer', (232, HEIGHT-56, 1184, 44), 'INTERPRETATION  /  ' + text, '12pt', MUTED)


def metric_card(page, key, position, measure, label):
    return visual(page, key, 'card', position, {'Values': [m(measure)]}, heading=label,
        objects={'labels': [{'properties': {'fontSize': lit('32D'), 'fontFamily': lit("'Segoe UI'"), 'bold': lit('true'), 'color': fill(INK), 'labelDisplayUnits': lit('1D')}}],
                 'categoryLabels': [{'properties': {'show': lit('false')}}]})


def takeaway(page, text, y=256):
    return textbox(page, 'takeaway', (232, y, 1184, 54), text, '12pt', INK, True, '#E3F1EF')


def note_tile(page, key, x, width, value, label):
    result = textbox(page, key, (x, 136, width, 100), '', background='#FFFFFF')
    result[1]['visual']['objects']['general'][0]['properties']['paragraphs'] = [
        {'textRuns': [{'value': value, 'textStyle': {'fontSize': '28pt', 'fontFamily': 'Segoe UI', 'fontWeight': 'bold', 'color': INK}}]},
        {'textRuns': [{'value': label, 'textStyle': {'fontSize': '12pt', 'fontFamily': 'Segoe UI', 'color': MUTED}}]},
    ]
    return result


def audience_filter():
    return {'filter': {'Version': 2, 'From': [{'Name': 'f', 'Entity': 'funnel_by_segment', 'Type': 0}],
        'Where': [{'Condition': {'In': {'Expressions': [{'Column': {'Expression': {'SourceRef': {'Source': 'f'}},
            'Property': 'dimension'}}], 'Values': [[{'Literal': {'Value': "'New vs returning'"}}]]}}}]}}


def page_one(kpis):
    p = PAGES[0][0]
    period = f"{pd.Timestamp(kpis.first_date):%d %b %Y} - {pd.Timestamp(kpis.last_date):%d %b %Y}"
    return p, PAGES[0][1], [
        *chrome(p, 'The purchase journey', 'Where buyers are lost, what the opportunity is, and where to focus  |  ' + period),
        *[metric_card(p, 'kpi-' + measure, (232 + i*300, 136, 284, 100), measure, label)
          for i, (measure, label) in enumerate([('Total sessions', 'Sessions analysed'), ('Total orders', 'Valid orders'),
              ('Session conversion', 'Session conversion'), ('Average order value', 'Average order value')])],
        takeaway(p, 'THE OPPORTUNITY  /  Four in five sessions record no product view. Validate tracking, then test discovery for new visitors.'),
        visual(p, 'funnel', 'clusteredBarChart', (232, 330, 400, 380),
            {'Category': [c('funnel_overall', 'step')], 'Y': [caption(m('Funnel sessions'), 'Sessions')]},
            heading='01  Sessions by purchase step', sort=field('funnel_overall', 'step'),
            objects=chart_style()),
        visual(p, 'stake', 'clusteredBarChart', (648, 330, 768, 380),
            {'Category': [c('revenue_at_stake', 'step')], 'Y': [caption(m('USD at stake (low)'), 'Low'),
                caption(m('USD at stake (base)'), 'Base'), caption(m('USD at stake (high)'), 'December')]},
            heading='02  What could +1 percentage point be worth?', sort=field('revenue_at_stake', 'step'), objects=chart_style()),
        textbox(p, 'scenario-note', (648, 716, 768, 44), 'USD per 30 days. Low/base/December are business scenarios, not statistical intervals.', '12pt', MUTED),
        textbox(p, 'audience-heading', (232, 784, 800, 44), '03  Which audience needs attention?', '16pt', INK, True),
        visual(p, 'dimension', 'slicer', (1096, 760, 320, 96), {'Values': [c('funnel_by_segment', 'dimension')]},
            heading='Compare by', objects={'data': [{'properties': {'mode': lit("'Dropdown'")}}],
                'items': [{'properties': {'textSize': lit('12D'), 'fontFamily': lit("'Segoe UI'")}}],
                'header': [{'properties': {'show': lit('false')}}],
                'general': [{'properties': {'selfFilterEnabled': lit('false'), 'filter': audience_filter()}}]}),
        visual(p, 'segments', 'pivotTable', (232, 866, 1184, 134),
            {'Rows': [caption(c('funnel_by_segment', 'segment'), 'Audience')], 'Columns': [c('funnel_by_segment', 'step')],
             'Values': [m('Step conversion')]}, objects=grid_style(True), sort=field('funnel_by_segment', 'step')),
        footer(p, 'Funnel counts event presence within a session, not strict sequence. Orders and purchasing sessions are different units.'),
    ]


def page_two():
    p = PAGES[1][0]
    t = load_tables()
    act = t['activation_odds'].set_index('term').loc['Added to cart in first session']
    power = t['power_table'].loc[lambda d: d.relative_mde == .05].iloc[0]
    retention = grid_style(True)
    retention['values'].extend(gradient('Retention rate')['values'])
    return p, PAGES[1][1], [
        *chrome(p, 'Customers, intent & the next test', 'Understand who returns, what predicts purchase, and how to size the discovery experiment'),
        note_tile(p, 'activation-signal', 232, 584, f'{act.odds_ratio:.2f}x adjusted odds', 'First-session add to cart predicts later purchase'),
        note_tile(p, 'test-plan', 832, 584, f'{int(power.n_per_arm):,} per arm  /  {int(power.weeks_needed)} weeks', 'To detect a 5% relative product-view lift'),
        visual(p, 'odds', 'tableEx', (232, 258, 550, 342),
            {'Values': [caption(c('activation_odds', 'term'), 'First-session signal'), m('Odds ratio'),
                caption(m('CI low'), 'CI low'), caption(m('CI high'), 'CI high')]},
            heading='01  Signals of a later purchase', objects=grid_style()),
        visual(p, 'retention', 'pivotTable', (798, 258, 618, 342),
            {'Rows': [caption(c('retention_cohorts', 'cohort_week'), 'First week')],
             'Columns': [caption(c('retention_cohorts', 'week_number'), 'Week')], 'Values': [m('Retention rate')]},
            heading='02  Do new visitors return?', objects=retention),
        textbox(p, 'odds-note', (232, 608, 550, 50), 'First-session non-buyers, followed for 30 days. Adjusted odds ratios with 95% intervals; predictive, not causal.', '12pt', MUTED),
        textbox(p, 'retention-note', (798, 608, 618, 50), 'Weekly cohort activity. Empty cells can reflect no recorded activity or incomplete follow-up.', '12pt', MUTED),
        visual(p, 'channels', 'clusteredBarChart', (232, 670, 384, 330),
            {'Category': [c('channel_quality', 'channel')], 'Y': [caption(m('Share of users'), 'Visitors'), caption(m('Share of revenue'), '56-day revenue')]},
            heading='03  Acquisition quality', objects=chart_style(precision=1)),
        visual(p, 'promo', 'clusteredColumnChart', (632, 670, 384, 330),
            {'Category': [c('promo_comparison', 'basis')], 'Series': [c('promo_comparison', 'group')], 'Y': [m('Promo conversion')]},
            heading='04  Promotions & conversion', sort=field('promo_comparison', 'basis'), objects=chart_style(precision=1)),
        visual(p, 'power', 'tableEx', (1032, 670, 384, 330),
            {'Values': [caption(c('power_table', 'relative_mde'), 'Target lift'), m('Users per arm'), m('Weeks needed')]},
            heading='05  Experiment sizing', objects=grid_style()),
        footer(p, 'Channels are first-touch; promotions are observational. Test sizing: 80% power, two-sided alpha 5%, equal allocation.'),
    ]


def page_three():
    p = PAGES[2][0]
    t = load_tables()
    k = t['kpis'].iloc[0]
    f = t['funnel_overall'].set_index('step')
    missing = t['discovery_landing'].loc[lambda d: d.landing_page == '[No page_view]', 'sessions'].sum()
    return p, PAGES[2][1], [
        *chrome(p, 'Inside the discovery gap', 'Observed landing pages, product-view coverage and where non-viewers finish  |  Funnel window'),
        note_tile(p, 'no-view', 232, 384, f'{1-f.loc["View item", "share_of_sessions"]:.1%}', 'Sessions without a product-view event'),
        note_tile(p, 'no-page', 632, 384, f'{missing/k.sessions:.1%}', 'Sessions without any page-view event'),
        note_tile(p, 'homepage', 1032, 384, f'{t["discovery_landing"].iloc[0].share_of_sessions:.1%}', 'Sessions first seen on Home'),
        takeaway(p, 'BEFORE TESTING  /  Product-titled pages sometimes lack view_item. Confirm instrumentation before treating missing views as navigation failure.'),
        visual(p, 'landings', 'clusteredBarChart', (232, 330, 584, 344),
            {'Category': [caption(c('discovery_landing', 'page_label'), 'Landing page')], 'Y': [m('Landing sessions')]},
            heading='01  Where do sessions begin?  |  Top 8 titles', objects=chart_style(),
            sort=field('discovery_landing', 'Landing sessions', 'Measure'), descending=True),
        visual(p, 'exits', 'clusteredBarChart', (832, 330, 584, 344),
            {'Category': [caption(c('discovery_exits', 'page_label'), 'Last page')], 'Y': [m('Exit sessions')]},
            heading='02  Where do non-viewers finish?  |  Top 8', objects=chart_style(),
            sort=field('discovery_exits', 'Exit sessions', 'Measure'), descending=True),
        visual(p, 'landing-rates', 'tableEx', (232, 698, 1184, 302),
            {'Values': [caption(c('discovery_landing', 'page_label'), 'Observed landing title'), m('Landing sessions'),
                caption(m('Landing view rate'), 'Records a product view'), caption(m('Landing order rate'), 'Session order rate')]},
            heading='03  Compare product-view coverage across landing pages', objects=grid_style(),
            sort=field('discovery_landing', 'Landing sessions', 'Measure'), descending=True),
        footer(p, 'First/last recorded page_view titles are not unique URLs or verified acquisition pages. Absence of an event is not proof of intent.'),
    ]


def page_four():
    p = PAGES[3][0]
    t = load_tables()
    k = t['kpis'].iloc[0]
    days = (pd.Timestamp(k.last_date)-pd.Timestamp(k.first_date)).days+1
    draws = json.loads((ROOT / 'docs/evidence/revenue_bootstrap.json').read_text())['repetitions']
    latest = t['tracking_daily'].sort_values('event_date').iloc[-1]
    latest_day = pd.Timestamp(latest.event_date).strftime('%d %b %Y')
    cart_style = chart_style(dense=True)
    cart_style['valueAxis'][0]['properties']['end'] = lit('2500D')
    return p, PAGES[3][1], [
        *chrome(p, 'Trust the evidence, bound the claim', 'Tracking coverage, sampling uncertainty and sensitivity to analytical definitions'),
        note_tile(p, 'reliable-days', 232, 384, f'{days} reporting days', '26 Nov 2020 - 25 Jan 2021 funnel window'),
        note_tile(p, 'source-days', 632, 384, f'{len(t["tracking_daily"])} source days', 'Daily audit preserves the full raw period'),
        note_tile(p, 'bootstrap-draws', 1032, 384, f'{draws:,} resamples', 'Whole users, with all their sessions retained'),
        takeaway(p, 'CONFIDENCE WITH LIMITS  /  Discovery leads under the +1-point model. Its sampling interval does not establish causal revenue impact.'),
        visual(p, 'cart-tracking', 'lineChart', (232, 330, 584, 300),
            {'Category': [c('tracking_daily', 'event_date')], 'Y': [m('Daily cart events')]},
            heading='01  Daily add-to-cart tracking', objects=cart_style, sort=field('tracking_daily', 'event_date')),
        visual(p, 'id-coverage', 'lineChart', (832, 330, 584, 300),
            {'Category': [c('tracking_daily', 'event_date')], 'Y': [m('Valid order ID coverage')]},
            heading='02  Purchase events with valid order IDs', objects=chart_style(dense=True), sort=field('tracking_daily', 'event_date')),
        textbox(p, 'latest-cart', (232, 640, 584, 40), f'Latest: {latest_day} | {latest.add_to_cart:,.0f} cart events', '12pt', INK, True),
        textbox(p, 'latest-coverage', (832, 640, 584, 40), f'Latest: {latest_day} | {latest.valid_purchase_share:.0%} valid order IDs', '12pt', INK, True),
        visual(p, 'sampling', 'tableEx', (232, 694, 584, 306),
            {'Values': [caption(c('revenue_bootstrap', 'step'), 'Stage'), caption(m('Bootstrap estimate'), 'USD / 30d'),
                caption(m('Bootstrap lower bound'), '95% low'), caption(m('Bootstrap upper bound'), '95% high')]},
            heading='03  Sampling uncertainty in the scenario', objects=grid_style(), sort=field('revenue_bootstrap', 'step')),
        visual(p, 'sensitivity', 'tableEx', (832, 694, 584, 306),
            {'Values': [caption(c('definition_sensitivity', 'definition'), 'Definition'),
                caption(m('Sensitivity orders'), 'Orders'), caption(m('Sensitivity conversion'), 'Conversion'),
                caption(m('Sensitivity view rate'), 'View rate')]},
            heading='04  Do definitions change the picture?', objects=grid_style()),
        footer(p, 'The audit misses partial recovery on 16-19 and 25 Nov. The 26 Nov start also relies on daily inspection; bootstrap CIs are conditional.'),
    ]


def build_report(tables):
    shutil.rmtree(REPORT / 'definition', ignore_errors=True)
    theme = 'MerchAnalytics'
    theme_path = REPORT / 'StaticResources/SharedResources/BaseThemes'
    palette = json.loads((theme_path / 'CY24SU06.json').read_text(encoding='utf-8'))
    palette.update(name=theme, dataColors=[BLUE, TEAL, '#D99338', '#93B9EC', '#7A8DA5', '#AB6A83'],
                   background='#FFFFFF', foreground=INK, tableAccent=BLUE)
    palette['textClasses'] = {
        'callout': {'fontSize': 32, 'fontFace': 'Segoe UI', 'color': INK},
        'title': {'fontSize': 28, 'fontFace': 'Segoe UI', 'color': INK},
        'header': {'fontSize': 16, 'fontFace': 'Segoe UI', 'color': INK},
        'label': {'fontSize': 12, 'fontFace': 'Segoe UI', 'color': MUTED},
        'largeTitle': {'fontSize': 16, 'fontFace': 'Segoe UI', 'color': INK},
    }
    write_json(theme_path / f'{theme}.json', palette)
    write_json(REPORT / 'definition.pbir', {
        '$schema': f'{SCHEMA}/item/report/definitionProperties/1.0.0/schema.json',
        'version': '4.0', 'datasetReference': {'byPath': {'path': f'../{NAME}.SemanticModel'}}})
    write_json(REPORT / 'definition/version.json', {
        '$schema': f'{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json', 'version': '2.0.0'})
    write_json(REPORT / 'definition/report.json', {
        '$schema': f'{SCHEMA}/item/report/definition/report/3.3.0/schema.json',
        'themeCollection': {'baseTheme': {'name': theme, 'reportVersionAtImport': {
            'visual': '1.1.0', 'page': '1.1.0', 'report': '3.3.0'}, 'type': 'SharedResources'}},
        'resourcePackages': [{'name': 'SharedResources', 'type': 'SharedResources',
                              'items': [{'name': theme, 'path': f'BaseThemes/{theme}.json', 'type': 'BaseTheme'}]}],
        'settings': {'useStylableVisualContainerHeader': True, 'defaultDrillFilterOtherVisuals': True,
                     'allowChangeFilterTypes': True, 'useEnhancedTooltips': True,
                     'useDefaultAggregateDisplayName': True, 'locale': 'en-US'}})
    pages = [page_one(tables['kpis'].iloc[0]), page_two(), page_three(), page_four()]
    write_json(REPORT / 'definition/pages/pages.json', {
        '$schema': f'{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json',
        'pageOrder': [p for p, _, _ in pages], 'activePageName': pages[0][0]})
    for name, display, visuals in pages:
        folder = REPORT / 'definition/pages' / name
        write_json(folder / 'page.json', {
            '$schema': f'{SCHEMA}/item/report/definition/page/1.1.0/schema.json', 'name': name,
            'displayName': display, 'displayOption': 'FitToWidth', 'height': HEIGHT, 'width': WIDTH,
            'objects': {'background': [{'properties': {'color': fill(PAPER), 'transparency': lit('0D')}}]}})
        ordered = sorted(visuals, key=lambda v: (0 if v[1]['visual']['visualType'] == 'actionButton' else 1, v[1]['position']['y'], v[1]['position']['x']))
        for order, (vname, content) in enumerate(ordered, start=1):
            content['position']['tabOrder'] = order
            write_json(folder / 'visuals' / vname / 'visual.json', content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regenerate', action='store_true', help='Replace existing report/model definitions after backing them up')
    args = parser.parse_args()
    if (MODEL.exists() or (REPORT / 'definition').exists()) and not args.regenerate:
        print('Preserved existing Power BI project. CSVs can be refreshed in Desktop; use --regenerate to replace definitions.')
        return
    if args.regenerate:
        from datetime import datetime, timezone
        backup = ROOT / 'data/dashboard_backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True)
        for source in [MODEL, REPORT]:
            if source.exists():
                shutil.copytree(source, backup / source.name)
        if (DASH / f'{NAME}.pbip').exists():
            shutil.copy2(DASH / f'{NAME}.pbip', backup)
        print(f'Backed up existing Power BI project to {backup}')
    tables = load_tables()
    build_model(tables)
    build_report(tables)
    write_json(DASH / f'{NAME}.pbip', {
        '$schema': f'{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json',
        'version': '1.0', 'artifacts': [{'report': {'path': f'{NAME}.Report'}}], 'settings': {'enableAutoRecovery': True}})
    print(f'Wrote {NAME}.pbip with {len(tables)} tables and {len(MEASURES)} measures.')


if __name__ == '__main__':
    main()
