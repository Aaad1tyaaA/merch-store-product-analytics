"""Prepare an ignored Power BI working copy with this checkout's absolute data path."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
NAME = 'merch-store'


def prepare_dashboard(root=ROOT, replace=False):
    root = Path(root).resolve()
    dashboard = root / 'dashboard'
    data = (dashboard / 'data').resolve()
    model = f'{NAME}.SemanticModel'
    report = f'{NAME}.Report'
    tables = list((dashboard / model / 'definition/tables').glob('*.tmdl'))
    if not tables:
        raise ValueError('The shared semantic model is missing.')
    missing = [p.stem for p in tables if not (data / f'{p.stem}.csv').is_file()
               or (data / f'{p.stem}.csv').stat().st_size == 0]
    if missing:
        raise ValueError('Missing or empty dashboard CSVs: ' + ', '.join(missing))
    local = dashboard / '.local'
    if replace and local.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = root / 'data/dashboard_backups' / stamp / 'local'
        if not local.resolve().is_relative_to(root) or not backup.resolve().is_relative_to(root):
            raise ValueError('The working copy and its backup must stay inside the project folder.')
        backup.parent.mkdir(parents=True)
        shutil.move(str(local), str(backup))
        print(f'Backed up the existing working copy: {backup}')
    if not local.exists():
        local.mkdir()
        for folder in (model, report):
            shutil.copytree(dashboard / folder, local / folder,
                            ignore=shutil.ignore_patterns('.pbi'))
        shutil.copy2(dashboard / f'{NAME}.pbip', local)
    parameter = local / model / 'definition/expressions.tmdl'
    source = parameter.read_text(encoding='utf-8')
    configured, count = re.subn(
        r'^expression DataFolder = "(?:[^"]|"")*" meta ',
        lambda _: 'expression DataFolder = "' + str(data).replace('"', '""') + '" meta ',
        source, flags=re.MULTILINE)
    if count != 1:
        raise ValueError('Expected exactly one DataFolder text parameter.')
    parameter.write_text(configured.rstrip() + '\n', encoding='utf-8', newline='\n')
    return local / f'{NAME}.pbip'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace', action='store_true',
                        help='Back up local Desktop edits, then copy the shared design again')
    args = parser.parse_args()
    try:
        project = prepare_dashboard(replace=args.replace)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Dashboard setup failed: {error}\n')
    print(f'Open in Power BI Desktop: {project}')
    print('Refresh once after the first setup. Existing local Desktop edits are preserved.')


if __name__ == '__main__':
    main()
