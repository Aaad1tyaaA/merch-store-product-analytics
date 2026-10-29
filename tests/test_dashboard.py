"""Power BI project checks: JSON and TMDL structure, field references, and every measure
reproduced in pandas against the analysis control totals."""
from pathlib import Path
import json
import re
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_dashboard import MEASURES, MODEL, REPORT, TABLES, load_tables  # noqa: E402


def tmdl_tables():
    """Columns and measures per table, checking the TMDL indentation as it goes."""
    out = {}
    for path in sorted((MODEL / 'definition/tables').glob('*.tmdl')):
        text = path.read_text(encoding='utf-8')
        assert '    ' not in text.replace('\t', ''), f'{path.name}: indent with tabs only'
        lines = text.splitlines()
        assert lines[0] == f'table {path.stem}'
        cols = [l.split()[1] for l in lines if l.startswith('\tcolumn ')]
        measures = [re.match(r"\tmeasure '?(.+?)'? = ", l).group(1) for l in lines if l.startswith('\tmeasure ')]
        assert sum(l.startswith('\tpartition ') for l in lines) == 1, f'{path.name}: one partition'
        out[path.stem] = {'columns': cols, 'measures': measures, 'text': text}
    return out


def test_every_json_file_parses():
    files = [p for p in (ROOT / 'dashboard').rglob('*') if p.suffix in {'.json', '.pbir', '.pbism', '.pbip'}]
    assert len(files) > 20
    for p in files:
        json.loads(p.read_text(encoding='utf-8'))


def test_tmdl_columns_match_csv_and_dax_references_resolve():
    model = tmdl_tables()
    data = load_tables()
    assert set(model) == set(TABLES)
    all_measures = {m for t in model.values() for m in t['measures']}
    for table, info in model.items():
        assert info['columns'] == list(data[table].columns), table
        assert re.findall(r'^\t\tsummarizeBy: (.+)$', info['text'], re.MULTILINE) == ['none'] * len(info['columns'])
        assert info['text'].count('annotation SummarizationSetBy = User') == len(info['columns'])
        assert '\t\tvariation ' not in info['text']
        dax = '\n'.join(l for l in info['text'].splitlines() if l.startswith('\tmeasure '))
        for ref_table, ref_col in re.findall(r"(\w+)\[(\w+)\]", dax):
            assert ref_col in model[ref_table]['columns'], f'{ref_table}[{ref_col}]'
        for ref in re.findall(r"(?<![\w\]])\[([^\]]+)\]", dax):
            assert ref in all_measures, ref
    columns = {c.lower() for t in model.values() for c in t['columns']}
    clashes = [m for m in all_measures if m.lower() in columns]
    assert not clashes, f'measure names must differ from column names: {clashes}'
    model_text = (MODEL / 'definition/model.tmdl').read_text(encoding='utf-8')
    assert all(f'ref table {t}' in model_text for t in TABLES)
    assert 'annotation __PBI_TimeIntelligenceEnabled = 0' in model_text
    expression = (MODEL / 'definition/expressions.tmdl').read_text(encoding='utf-8')
    assert re.search(r'^expression DataFolder = "" meta ', expression, re.MULTILINE), \
        'The shared template must not contain a machine-specific path; use setup_dashboard.py.'


def test_visual_fields_exist_in_model():
    model = tmdl_tables()
    visuals = list((REPORT / 'definition/pages').rglob('visual.json'))
    assert len(visuals) >= 14
    for path in visuals:
        text = path.read_text(encoding='utf-8')
        for kind, entity, prop in re.findall(r'"(Column|Measure)": \{\s*"Expression": \{\s*"SourceRef": \{\s*"Entity": "(\w+)"\s*\}\s*\},\s*"Property": "([^"]+)"', text):
            key = 'columns' if kind == 'Column' else 'measures'
            assert prop in model[entity][key], f'{path.parent.name}: {entity}.{prop}'


def test_measures_match_analysis_totals():
    t = load_tables()
    kpis = pd.read_csv(ROOT / 'app/data/kpis.csv').iloc[0]
    values = {name: fn(t) for name, (_, _, _, fn) in MEASURES.items() if fn}
    assert values['Total sessions'] == kpis.sessions
    assert values['Total orders'] == kpis.orders
    assert values['Total revenue'] == pytest.approx(kpis.revenue_usd)
    assert values['Average order value'] == pytest.approx(kpis.aov, abs=1e-9)
    # conversion from the funnel table equals conversion computed from sessions directly
    assert values['Session conversion'] == pytest.approx(kpis.session_conversion, abs=1e-12)
    assert values['Funnel sessions'] == t['funnel_overall'].sessions.sum()
    assert values['Share of users'] == pytest.approx(1)
    assert values['Share of revenue'] == pytest.approx(1)


def test_actual_dax_matches_the_expressions_with_control_totals():
    model = tmdl_tables()
    for name, (owner, dax, _, _) in MEASURES.items():
        actual = re.search(r"^\tmeasure '?" + re.escape(name) + r"'? = (.+)$",
                           model[owner]['text'], re.MULTILINE)
        assert actual is not None, name
        assert ' '.join(actual.group(1).split()) == ' '.join(dax.split()), name


def test_table_measure_projections_are_active():
    from build_dashboard import proj
    assert proj('activation_odds', 'Odds ratio', 'Measure')['active'] is True
    for path in (REPORT / 'definition/pages').rglob('visual.json'):
        visual = json.loads(path.read_text(encoding='utf-8'))['visual']
        if visual['visualType'] == 'tableEx':
            projections = visual['query']['queryState']['Values']['projections']
            assert all(p.get('active') is True for p in projections), path


def test_generator_preserves_existing_desktop_changes_by_default(tmp_path, monkeypatch):
    import build_dashboard as builder
    model = tmp_path / 'SemanticModel'
    model.mkdir()
    saved = model / 'manual-edit.tmdl'
    saved.write_text('keep this')
    monkeypatch.setattr(builder, 'MODEL', model)
    monkeypatch.setattr(builder, 'REPORT', tmp_path / 'Report')
    monkeypatch.setattr(sys, 'argv', ['build_dashboard.py'])
    builder.main()
    assert saved.read_text() == 'keep this'


def test_explicit_regeneration_backs_up_before_replacing(tmp_path, monkeypatch):
    import build_dashboard as builder
    import shutil
    model = tmp_path / 'dashboard/model'
    model.mkdir(parents=True)
    (model / 'manual.tmdl').write_text('original')
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'DASH', model.parent)
    monkeypatch.setattr(builder, 'MODEL', model)
    monkeypatch.setattr(builder, 'REPORT', model.parent / 'report')
    monkeypatch.setattr(builder, 'load_tables', lambda: {})
    monkeypatch.setattr(builder, 'build_model', lambda tables: shutil.rmtree(model))
    monkeypatch.setattr(builder, 'build_report', lambda tables: None)
    monkeypatch.setattr(sys, 'argv', ['build_dashboard.py', '--regenerate'])
    builder.main()
    backups = list((tmp_path / 'data/dashboard_backups').glob('*/model/manual.tmdl'))
    assert len(backups) == 1 and backups[0].read_text() == 'original'
    assert not model.exists()


def test_generated_model_has_portable_parameter_and_no_automatic_dates(tmp_path, monkeypatch):
    import build_dashboard as builder
    monkeypatch.setattr(builder, 'MODEL', tmp_path / 'model')
    builder.build_model(builder.load_tables())
    definition = builder.MODEL / 'definition'
    assert 'expression DataFolder = "" meta ' in (definition / 'expressions.tmdl').read_text()
    assert 'annotation __PBI_TimeIntelligenceEnabled = 0' in (definition / 'model.tmdl').read_text()
    assert {p.stem for p in (definition / 'tables').glob('*.tmdl')} == set(TABLES)
    for path in (definition / 'tables').glob('*.tmdl'):
        text = path.read_text()
        assert 'summarizeBy: sum' not in text
        assert 'annotation SummarizationSetBy = Automatic' not in text
        assert '\t\tvariation ' not in text


def test_dashboard_layout_and_tables_have_readable_presentation_defaults():
    for page in (REPORT / 'definition/pages').glob('*/page.json'):
        config = json.loads(page.read_text(encoding='utf-8'))
        visuals = [json.loads(p.read_text(encoding='utf-8')) for p in page.parent.glob('visuals/*/visual.json')]
        text = ' '.join(json.dumps(v) for v in visuals)
        assert 'PRODUCT ANALYTICS' in text
        assert 'INTERPRETATION' in text
        for v in visuals:
            pos = v['position']
            assert 0 <= pos['x'] < pos['x'] + pos['width'] <= config['width']
            assert 0 <= pos['y'] < pos['y'] + pos['height'] <= config['height']
            if v['visual']['visualType'] == 'tableEx':
                assert v['visual']['objects']['total'][0]['properties']['totals']['expr']['Literal']['Value'] == 'false'
    model = (MODEL / 'definition/tables/power_table.tmdl').read_text(encoding='utf-8')
    assert '\t\tformatString: 0.0%' in model


def test_four_pages_have_complete_navigation_and_no_content_overlap():
    pages = REPORT / 'definition/pages'
    metadata = json.loads((pages / 'pages.json').read_text())
    assert len(metadata['pageOrder']) == 4
    assert len(set(metadata['pageOrder'])) == 4
    for page in metadata['pageOrder']:
        targets = []
        blocks = []
        for path in (pages / page).glob('visuals/*/visual.json'):
            visual = json.loads(path.read_text())
            obj = visual['visual']
            pos = visual['position']
            if obj['visualType'] == 'actionButton':
                link = obj['visualContainerObjects']['visualLink'][0]['properties']
                assert link['type']['expr']['Literal']['Value'] == "'PageNavigation'"
                targets.append(link['navigationSection']['expr']['Literal']['Value'].strip("'"))
                assert pos['width'] >= 160 and pos['height'] >= 44
            elif pos['x'] >= 232:
                blocks.append(pos)
        assert set(targets) == set(metadata['pageOrder'])
        for i, a in enumerate(blocks):
            for b in blocks[i+1:]:
                width = min(a['x']+a['width'], b['x']+b['width']) - max(a['x'], b['x'])
                height = min(a['y']+a['height'], b['y']+b['height']) - max(a['y'], b['y'])
                assert width <= 0 or height <= 0, (page, a, b)


def test_new_pages_reconcile_to_published_evidence():
    tables = load_tables()
    source = ROOT / 'docs/evidence'
    landing = pd.read_csv(source / 'landing_pages.csv').nlargest(8, 'sessions')
    assert tables['discovery_landing'].sessions.sum() == landing.sessions.sum()
    assert set(tables['discovery_landing'].landing_page) == set(landing.landing_page)
    assert len(tables['tracking_daily']) == 92
    expected = pd.read_csv(source / 'revenue_bootstrap.csv')
    pd.testing.assert_frame_equal(tables['revenue_bootstrap'][list(expected.columns)], expected)


def test_readable_type_scale_chart_values_and_tab_order():
    report = json.loads((REPORT / 'definition/report.json').read_text())
    assert report['settings']['locale'] == 'en-US'
    chart_types = {'clusteredBarChart', 'clusteredColumnChart', 'lineChart'}
    for page in (REPORT / 'definition/pages').glob('*/page.json'):
        assert json.loads(page.read_text())['displayOption'] == 'FitToWidth'
        order = []
        for path in page.parent.glob('visuals/*/visual.json'):
            visual = json.loads(path.read_text())
            order.append(visual['position']['tabOrder'])
            obj = visual['visual']
            if obj['visualType'] in chart_types:
                labels = obj['objects']['labels'][0]['properties']
                assert labels['show']['expr']['Literal']['Value'] == 'true'
                assert float(labels['fontSize']['expr']['Literal']['Value'].rstrip('D')) >= 12
                assert labels['labelDisplayUnits']['expr']['Literal']['Value'] == '1D'
                assert obj['visualContainerObjects']['general'][0]['properties']['altText']
                if obj['visualType'] == 'lineChart':
                    assert labels['labelDensity']['expr']['Literal']['Value'] == '20D'
                    assert labels['labelPosition']['expr']['Literal']['Value'] == "'Above'"
                    assert labels['enableBackground']['expr']['Literal']['Value'] == 'true'
                else:
                    assert labels['labelDensity']['expr']['Literal']['Value'] == '100D'
                    assert obj['objects']['categoryAxis'][0]['properties']['maxMarginFactor']['expr']['Literal']['Value'] == '45D'
            if obj['visualType'] in {'tableEx', 'pivotTable'}:
                assert obj['objects']['values'][0]['properties']['fontSize']['expr']['Literal']['Value'] == '12D'
            if obj['visualType'] == 'textbox':
                for para in obj['objects']['general'][0]['properties']['paragraphs']:
                    for run in para['textRuns']:
                        assert float(run['textStyle']['fontSize'].rstrip('pt')) >= 12
        assert sorted(order) == list(range(1, len(order)+1))


def test_text_palette_meets_normal_text_contrast():
    from build_dashboard import INK, MUTED, PAPER, TEAL
    def luminance(color):
        rgb = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
        linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]
        return sum(c*w for c, w in zip(linear, [.2126, .7152, .0722]))
    for foreground, background in [(INK, '#FFFFFF'), (MUTED, PAPER), (INK, '#EAF0F7'),
                                   ('#FFFFFF', TEAL), ('#A4B6CB', INK), ('#8FDDD0', INK),
                                   (INK, '#B8D4F4'), ('#D8E3F2', '#193454'), ('#D8E3F2', '#246B82')]:
        light, dark = sorted([luminance(foreground), luminance(background)], reverse=True)
        assert (light+.05)/(dark+.05) >= 4.5, (foreground, background)
