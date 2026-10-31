"""Smoke tests for the Streamlit app and its statistics, using only app/data."""
from pathlib import Path
import sys
import pytest

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
from stats import n_per_arm, srm_check, weeks_needed  # noqa: E402


def test_sample_size_matches_textbook_case():
    assert 3800 < n_per_arm(0.10, 0.20) < 3900
    assert weeks_needed(1000, 100_000) == 2


def test_srm_flags_a_broken_split():
    assert srm_check([10_000, 10_100])[1] is False
    assert srm_check([10_000, 9_000])[1] is True


def test_app_runs_and_planner_responds():
    at = AppTest.from_file(str(APP / 'streamlit_app.py'), default_timeout=60).run()
    assert not at.exception
    assert at.metric[0].value == '248,669'
    assert len(at.tabs) == 5
    assert len(at.get('vega_lite_chart')) >= 12
    assert any('Validate tracking first' in item.value for item in at.info)
    at.selectbox[0].select('Device').run()
    assert not at.exception
    at.number_input[3].set_value(9_000).run()
    assert at.error and 'SRM detected' in at.error[0].value


def test_empty_segment_selection_keeps_other_analytics_available():
    at = AppTest.from_file(str(APP / 'streamlit_app.py'), default_timeout=60).run()
    at.multiselect[0].set_value([]).run()
    assert not at.exception
    assert any('Pick at least one segment' in item.value for item in at.info)
    assert len(at.get('vega_lite_chart')) >= 10


def test_high_baseline_skips_impossible_comparison_grid_rows():
    at = AppTest.from_file(str(APP / 'streamlit_app.py'), default_timeout=60).run()
    at.number_input[0].set_value(90.0).run()
    assert not at.exception
    at.number_input[1].set_value(20.0).run()
    assert not at.exception
    assert any('Rates must be between' in e.value for e in at.error)


@pytest.mark.parametrize('args', [(.1, 0), (.1, -.1), (.1, .1, 0), (.1, .1, .05, 1), (float('nan'), .1)])
def test_sample_size_rejects_invalid_inputs(args):
    with pytest.raises(ValueError):
        n_per_arm(*args)


@pytest.mark.parametrize('counts,shares', [([0, 0], None), ([1, -1], None), ([1, 2], [.5]), ([1, 2], [0, 1])])
def test_srm_rejects_invalid_counts_and_allocations(counts, shares):
    with pytest.raises(ValueError):
        srm_check(counts, shares)
