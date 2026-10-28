"""Generate the Power BI project (PBIP: PBIR report + TMDL model) in dashboard/ from dashboard/data/*.csv.

Measures are defined once here with a pandas equivalent, so tests can check every Power BI
number against the analysis without opening Power BI.
"""
from pathlib import Path
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

TABLES = ['kpis', 'funnel_overall', 'funnel_by_segment', 'revenue_at_stake', 'activation_odds',
          'retention_cohorts', 'channel_quality', 'promo_comparison', 'power_table']
DATE_COLUMNS = {'cohort_week', 'first_date', 'last_date'}
SORT_BY = {('funnel_overall', 'step'): 'step_order', ('funnel_by_segment', 'step'): 'step_order',
           ('revenue_at_stake', 'step'): 'step_order', ('promo_comparison', 'basis'): 'basis_order'}
ROW_FILTER = {'retention_cohorts': 'each [week_number] >= 1 and [week_number] <= 8'}


def step_sessions(t, step):
    f = t['funnel_overall']
    return f.loc[f.step_order == step, 'sessions'].sum()


# name: (table, DAX, format, pandas equivalent of the measure's total)
MEASURES = {
    'Sessions': ('kpis', 'SUM(kpis[sessions])', '#,0', lambda t: t['kpis'].sessions.sum()),
    'Orders': ('kpis', 'SUM(kpis[orders])', '#,0', lambda t: t['kpis'].orders.sum()),
    'Revenue': ('kpis', 'SUM(kpis[revenue_usd])', '\\$#,0', lambda t: t['kpis'].revenue_usd.sum()),
    'AOV': ('kpis', 'DIVIDE([Revenue], [Orders])', '\\$#,0.00', lambda t: t['kpis'].revenue_usd.sum() / t['kpis'].orders.sum()),
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
    'Retention': ('retention_cohorts', 'AVERAGE(retention_cohorts[retention])', '0.0%', None),
    'Share of users': ('channel_quality', 'SUM(channel_quality[share_of_users])', '0.0%', lambda t: t['channel_quality'].share_of_users.sum()),
    'Share of revenue': ('channel_quality', 'SUM(channel_quality[share_of_revenue])', '0.0%', lambda t: t['channel_quality'].share_of_revenue.sum()),
    'Conversion': ('promo_comparison', 'AVERAGE(promo_comparison[conversion])', '0.00%', None),
    'Users per arm': ('power_table', 'SUM(power_table[n_per_arm])', '#,0', None),
    'Weeks needed': ('power_table', 'SUM(power_table[weeks_needed])', '0', None),
}


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
        lines += ['', '\t\tannotation SummarizationSetBy = Automatic', '']
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

{refs}
''')
    write_text(MODEL / 'definition/expressions.tmdl', f'''/// Folder holding the exported CSVs: <repository>\\dashboard\\data
expression DataFolder = "C:\\merch-store-product-analytics\\dashboard\\data" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]
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
            **({'active': True} if kind == 'Column' else {})}


def m(name):
    return proj(MEASURES[name][0], name, 'Measure')


def c(table, column):
    return proj(table, column)


def title(text):
    return {'title': [{'properties': {'show': lit('true'), 'text': lit("'" + text.replace("'", "''") + "'")}}]}


def visual(page, key, kind, pos, roles=None, objects=None, heading=None, sort=None):
    x, y, w, h = pos
    v = {'visualType': kind}
    if roles:
        v['query'] = {'queryState': {role: {'projections': items} for role, items in roles.items()}}
        if sort:
            v['query']['sortDefinition'] = {'sort': [{'field': sort, 'direction': 'Ascending'}], 'isDefaultSort': False}
    if objects:
        v['objects'] = objects
    if heading:
        v['visualContainerObjects'] = title(heading)
    v['drillFilterOtherVisuals'] = True
    name = short_id(page, key)
    z = 1000 + len(key) * 10 + int(name[:3], 16) % 9
    return name, {'$schema': f'{SCHEMA}/item/report/definition/visualContainer/1.1.0/schema.json', 'name': name,
                  'position': {'x': x, 'y': y, 'z': z, 'height': h, 'width': w, 'tabOrder': z}, 'visual': v}


def textbox(page, key, pos, text, size='16pt'):
    return visual(page, key, 'textbox', pos, objects={'general': [{'properties': {'paragraphs': [
        {'textRuns': [{'value': text, 'textStyle': {'fontWeight': 'bold', 'fontSize': size}}]}]}}]})


def gradient(measure):
    table = MEASURES[measure][0]
    return {'values': [{'properties': {'backColor': {'solid': {'color': {'expr': {'FillRule': {
        'Input': field(table, measure, 'Measure'),
        'FillRule': {'linearGradient2': {
            'min': {'color': {'Literal': {'Value': "'#FFFFFF'"}}},
            'max': {'color': {'Literal': {'Value': "'#2A78D6'"}}},
            'nullColoringStrategy': {'strategy': {'Literal': {'Value': "'asZero'"}}}}}}}}}}},
        'selector': {'data': [{'dataViewWildcard': {'matchingOption': 1}}], 'metadata': f'{table}.{measure}'}}]}


def page_one(kpis):
    p = 'where-we-lose-buyers'
    period = f"{pd.Timestamp(kpis.first_date):%d %b %Y} to {pd.Timestamp(kpis.last_date):%d %b %Y}"
    cards = [visual(p, f'card-{n}', 'card', (20 + i * 315, 60, 300, 100), {'Values': [m(n)]}, heading=n)
             for i, n in enumerate(['Sessions', 'Orders', 'Session conversion', 'AOV'])]
    return p, 'Where we lose buyers', [
        textbox(p, 'title', (20, 10, 1240, 45), f'Where we lose buyers: sessions {period}'),
        *cards,
        visual(p, 'funnel', 'funnel', (20, 175, 400, 530), {'Category': [c('funnel_overall', 'step')], 'Y': [m('Funnel sessions')]},
               heading='Sessions reaching each step', sort=field('funnel_overall', 'step')),
        visual(p, 'stake', 'clusteredBarChart', (430, 175, 420, 530),
               {'Category': [c('revenue_at_stake', 'step')], 'Y': [m('USD at stake (low)'), m('USD at stake (base)'), m('USD at stake (high)')]},
               heading='USD per 30 days from +1 point at each step', sort=field('revenue_at_stake', 'step')),
        visual(p, 'dimension', 'slicer', (860, 175, 400, 90), {'Values': [c('funnel_by_segment', 'dimension')]},
               objects={'data': [{'properties': {'mode': lit("'Dropdown'")}}],
                        'general': [{'properties': {'selfFilterEnabled': lit('false')}}]}, heading='Segment by'),
        visual(p, 'segments', 'pivotTable', (860, 275, 400, 430),
               {'Rows': [c('funnel_by_segment', 'segment')], 'Columns': [c('funnel_by_segment', 'step')], 'Values': [m('Step conversion')]},
               heading='Conversion from the previous step', sort=field('funnel_by_segment', 'step')),
    ]


def page_two():
    p = 'who-buys-and-what-to-test'
    return p, 'Who buys and what to test', [
        textbox(p, 'title', (20, 10, 1240, 45), 'Who buys and what to test'),
        visual(p, 'odds', 'tableEx', (20, 60, 420, 310),
               {'Values': [c('activation_odds', 'term'), m('Odds ratio'), m('CI low'), m('CI high')]},
               heading='Odds of buying within 30 days (first-session non-buyers)'),
        visual(p, 'retention', 'pivotTable', (450, 60, 810, 310),
               {'Rows': [c('retention_cohorts', 'cohort_week')], 'Columns': [c('retention_cohorts', 'week_number')], 'Values': [m('Retention')]},
               objects=gradient('Retention'), heading='Weekly retention of new users by first week'),
        visual(p, 'channels', 'clusteredBarChart', (20, 380, 420, 325),
               {'Category': [c('channel_quality', 'channel')], 'Y': [m('Share of users'), m('Share of revenue')]},
               heading='First-touch channel: share of new users vs 56-day revenue'),
        visual(p, 'promo', 'clusteredColumnChart', (450, 380, 390, 325),
               {'Category': [c('promo_comparison', 'basis')], 'Series': [c('promo_comparison', 'group')], 'Y': [m('Conversion')]},
               heading='Promotion clickers convert better, raw and adjusted', sort=field('promo_comparison', 'basis')),
        visual(p, 'power', 'tableEx', (850, 380, 410, 325),
               {'Values': [c('power_table', 'relative_mde'), m('Users per arm'), m('Weeks needed')]},
               heading='Test plan: users per arm and weeks by MDE'),
    ]


def build_report(tables):
    shutil.rmtree(REPORT / 'definition', ignore_errors=True)
    theme = 'CY24SU06'  # Power BI's built-in base theme, kept in StaticResources
    assert (REPORT / f'StaticResources/SharedResources/BaseThemes/{theme}.json').exists()
    write_json(REPORT / 'definition.pbir', {
        '$schema': f'{SCHEMA}/item/report/definitionProperties/1.0.0/schema.json',
        'version': '4.0', 'datasetReference': {'byPath': {'path': f'../{NAME}.SemanticModel'}}})
    write_json(REPORT / 'definition/version.json', {
        '$schema': f'{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json', 'version': '2.0.0'})
    write_json(REPORT / 'definition/report.json', {
        '$schema': f'{SCHEMA}/item/report/definition/report/1.1.0/schema.json',
        'themeCollection': {'baseTheme': {'name': theme, 'reportVersionAtImport': '5.56', 'type': 'SharedResources'}},
        'layoutOptimization': 'None',
        'resourcePackages': [{'name': 'SharedResources', 'type': 'SharedResources',
                              'items': [{'name': theme, 'path': f'BaseThemes/{theme}.json', 'type': 'BaseTheme'}]}],
        'settings': {'useStylableVisualContainerHeader': True, 'defaultDrillFilterOtherVisuals': True,
                     'allowChangeFilterTypes': True, 'useEnhancedTooltips': True, 'useDefaultAggregateDisplayName': True}})
    pages = [page_one(tables['kpis'].iloc[0]), page_two()]
    write_json(REPORT / 'definition/pages/pages.json', {
        '$schema': f'{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json',
        'pageOrder': [p for p, _, _ in pages], 'activePageName': pages[0][0]})
    for name, display, visuals in pages:
        folder = REPORT / 'definition/pages' / name
        write_json(folder / 'page.json', {
            '$schema': f'{SCHEMA}/item/report/definition/page/1.1.0/schema.json', 'name': name,
            'displayName': display, 'displayOption': 'FitToPage', 'height': 720, 'width': 1280})
        for vname, content in visuals:
            write_json(folder / 'visuals' / vname / 'visual.json', content)


def main():
    tables = load_tables()
    build_model(tables)
    build_report(tables)
    write_json(DASH / f'{NAME}.pbip', {
        '$schema': f'{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json',
        'version': '1.0', 'artifacts': [{'report': {'path': f'{NAME}.Report'}}], 'settings': {'enableAutoRecovery': True}})
    print(f'Wrote {NAME}.pbip with {len(tables)} tables and {len(MEASURES)} measures.')


if __name__ == '__main__':
    main()
