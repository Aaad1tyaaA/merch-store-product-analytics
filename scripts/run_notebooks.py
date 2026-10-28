"""Execute the implemented analysis notebooks with the current Python environment."""
from pathlib import Path
import sys

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager

ROOT = Path(__file__).resolve().parents[1]


def main():
    for path in sorted(ROOT.glob('[0-9][0-9]_*.ipynb')):
        notebook = nbformat.read(path, as_version=4)
        manager = KernelManager(kernel_name='python3')
        manager.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
        client = NotebookClient(notebook, km=manager, timeout=300,
                                resources={'metadata': {'path': str(ROOT)}})
        client.execute(cleanup_kc=True)
        nbformat.write(notebook, path)
        print(f'Executed {path.name}', flush=True)


if __name__ == '__main__':
    main()
