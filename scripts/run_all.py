"""Rebuild everything: download (only if files are missing), database and model, notebooks,
app and dashboard data, Power BI project and tests."""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_id', help='Google Cloud project used to run the BigQuery extraction')
    args = parser.parse_args()
    for command in [('scripts/download_bq.py', args.project_id), ('scripts/setup_db.py',),
                    ('scripts/run_notebooks.py',), ('scripts/export_app_data.py',),
                    ('scripts/build_dashboard.py',), ('-m', 'pytest', '-q', 'tests')]:
        subprocess.run([sys.executable, *command], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
