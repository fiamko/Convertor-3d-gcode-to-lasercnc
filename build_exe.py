"""Build a Windows EXE with its own Python/Tk runtime; no CMD launcher needed.
Install build dependencies locally first:
    python -m pip install --target .build-tools pyinstaller
Then run:
    python build_exe.py
"""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
for output in ('build','dist'):
    if not (root / output).resolve().is_relative_to(root):
        raise RuntimeError('Build output must stay inside the project directory.')
dist = root / ('build/exe-staging' if '--staged' in sys.argv else 'dist')
if not dist.resolve().is_relative_to(root): raise RuntimeError('Invalid output directory')
env = os.environ.copy()
env['PYTHONPATH'] = str(root / '.build-tools')
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
    '--onedir', '--windowed', '--name', 'PrevodnikNC',
    '--icon', str(root / 'PrevodnikNC.ico'),
    '--add-data', str(root / 'PrevodnikNC.ico') + ';.',
    '--distpath', str(dist), '--workpath', str(root / 'build'),
    '--specpath', str(root / 'build'), str(root / 'exe_entry.py')
], cwd=root, env=env, check=True)
exe = dist / 'PrevodnikNC' / 'PrevodnikNC.exe'
subprocess.run([str(exe), '--self-test'], cwd=root, check=True, timeout=60)
print('EXE verified:', exe)
