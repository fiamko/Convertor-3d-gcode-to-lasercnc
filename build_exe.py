"""Build a windowed Windows bundle. Default: one portable EXE; --onedir: folder."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--onedir',action='store_true',help='Build the development folder bundle instead of one EXE')
    parser.add_argument('--staged',action='store_true',help='Build under build/exe-staging, leaving installed EXEs alone')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    dist=root/('build/exe-staging' if args.staged else 'dist')
    work=root/'build'/('onedir' if args.onedir else 'onefile')
    for path in (dist,work):
        if not path.resolve().is_relative_to(root): raise RuntimeError('Build output must stay in the project')
    env=os.environ.copy()
    # Supports either a regular pip install or the historical project-local tools.
    env['PYTHONPATH']=str(root/'.build-tools')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean',
        '--onedir' if args.onedir else '--onefile','--windowed','--noupx',
        '--name','PrevodnikNC','--icon',str(root/'PrevodnikNC.ico'),
        '--distpath',str(dist),'--workpath',str(work),'--specpath',str(work)]
    for name,destination in [('PrevodnikNC.ico','.'),('docs','docs'),('LICENSE','.')]:
        command+=['--add-data',str(root/name)+os.pathsep+destination]
    subprocess.run(command+[str(root/'exe_entry.py')],cwd=root,env=env,check=True)
    exe=dist/'PrevodnikNC'/'PrevodnikNC.exe' if args.onedir else dist/'PrevodnikNC.exe'
    subprocess.run([str(exe),'--self-test'],cwd=root,check=True,timeout=120)
    print('EXE verified:',exe)


if __name__=='__main__': main()
