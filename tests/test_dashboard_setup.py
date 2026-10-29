"""A shareable template and a machine-specific working report stay separate."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from setup_dashboard import prepare_dashboard


@pytest.fixture
def project(tmp_path):
    dashboard = tmp_path / 'dashboard'
    model = dashboard / 'merch-store.SemanticModel/definition'
    (model / 'tables').mkdir(parents=True)
    (model / 'tables/kpis.tmdl').write_text('table kpis\n')
    (model / 'expressions.tmdl').write_text('expression DataFolder = "" meta [Type = "Text"]\n')
    (dashboard / 'merch-store.Report').mkdir()
    (dashboard / 'merch-store.Report/definition.pbir').write_text('{}')
    (dashboard / 'merch-store.pbip').write_text('{}')
    (dashboard / 'data').mkdir()
    (dashboard / 'data/kpis.csv').write_text('sessions\n1\n')
    return tmp_path


def test_setup_configures_only_local_copy_and_preserves_desktop_edits(project):
    result = prepare_dashboard(project)
    model = project / 'dashboard/merch-store.SemanticModel/definition/expressions.tmdl'
    local = result.parent / 'merch-store.SemanticModel/definition/expressions.tmdl'
    assert 'DataFolder = "" meta' in model.read_text()
    assert str((project / 'dashboard/data').resolve()) in local.read_text()
    edit = result.parent / 'merch-store.Report/desktop-edit.json'
    edit.write_text('keep my changes')
    assert prepare_dashboard(project) == result
    assert edit.read_text() == 'keep my changes'


def test_replace_backs_up_desktop_edits_before_copying_shared_design(project):
    result = prepare_dashboard(project)
    edit = result.parent / 'merch-store.Report/desktop-edit.json'
    edit.write_text('original')
    prepare_dashboard(project, replace=True)
    backups = list((project / 'data/dashboard_backups').glob('*/local/merch-store.Report/desktop-edit.json'))
    assert len(backups) == 1 and backups[0].read_text() == 'original'
    assert not edit.exists()


def test_missing_data_fails_before_creating_a_local_project(project):
    (project / 'dashboard/data/kpis.csv').unlink()
    with pytest.raises(ValueError, match='kpis'):
        prepare_dashboard(project)
    assert not (project / 'dashboard/.local').exists()
