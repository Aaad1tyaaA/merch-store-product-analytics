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
        dax = '\n'.join(l for l in info['text'].splitlines() if l.startswith('\tmeasure '))
        for ref_table, ref_col in re.findall(r"(\w+)\[(\w+)\]", dax):
            assert ref_col in model[ref_table]['columns'], f'{ref_table}[{ref_col}]'
        for ref in re.findall(r"(?<![\w\]])\[([^\]]+)\]", dax):
            assert ref in all_measures, ref
    model_text = (MODEL / 'definition/model.tmdl').read_text(encoding='utf-8')
    assert all(f'ref table {t}' in model_text for t in TABLES)


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
    assert values['Sessions'] == kpis.sessions
    assert values['Orders'] == kpis.orders
    assert values['Revenue'] == pytest.approx(kpis.revenue_usd)
    assert values['AOV'] == pytest.approx(kpis.aov, abs=1e-9)
    # conversion from the funnel table equals conversion computed from sessions directly
    assert values['Session conversion'] == pytest.approx(kpis.session_conversion, abs=1e-12)
    assert values['Funnel sessions'] == t['funnel_overall'].sessions.sum()
    assert values['Share of users'] == pytest.approx(1)
    assert values['Share of revenue'] == pytest.approx(1)
