"""Render docs/memo.md to docs/memo.pdf with a headless Chromium browser (Edge or Chrome)."""
from pathlib import Path
import shutil
import subprocess
import tempfile

import mistune

ROOT = Path(__file__).resolve().parents[1]
CSS = """@page { size: A4; margin: 9mm 12mm; }
body { font: 8.3pt/1.25 'Segoe UI', Arial, sans-serif; color: #0b0b0b; }
h1 { font-size: 15pt; margin: 0 0 4pt; } h2 { font-size: 10.5pt; margin: 9pt 0 3pt; color: #2a78d6; }
p, ul { margin: 0 0 4pt; } li { margin: 0 0 1pt; } table { border-collapse: collapse; width: 100%; margin: 3pt 0 4pt; }
th, td { border-bottom: 1px solid #ddd; padding: 2.5pt 4pt; text-align: left; vertical-align: top; } th { background: #f3f3f1; }
code { font-size: 8pt; }"""
BROWSERS = [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', 'google-chrome', 'chromium', 'msedge']


def main():
    body = mistune.html((ROOT / 'docs/memo.md').read_text(encoding='utf-8'))
    browser = next(b for b in BROWSERS if Path(b).exists() or shutil.which(b))
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / 'memo.html'
        page.write_text(f'<!doctype html><meta charset="utf-8"><style>{CSS}</style>{body}', encoding='utf-8')
        subprocess.run([browser, '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                        f'--print-to-pdf={ROOT / "docs/memo.pdf"}', page.as_uri()], check=True, capture_output=True)
    print('Wrote docs/memo.pdf')


if __name__ == '__main__':
    main()
