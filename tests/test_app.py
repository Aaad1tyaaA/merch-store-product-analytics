"""Smoke tests for the Streamlit app and its statistics, using only app/data."""
from pathlib import Path
import sys

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
    at.selectbox[0].select('Device').run()
    assert not at.exception
    at.number_input[3].set_value(9_000).run()
    assert at.error and 'SRM detected' in at.error[0].value
