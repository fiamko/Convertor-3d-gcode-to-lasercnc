"""Atomic local recovery snapshots. Original NC files are never overwritten."""
from pathlib import Path
import json
import os
import tempfile


def atomic_write_text(path, text):
    path=Path(path)
    temp=None
    try:
        handle=tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',dir=path.parent,prefix='.prevodnik-',suffix='.tmp',delete=False)
        temp=Path(handle.name)
        with handle:
            handle.write(text)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp,path)
    finally:
        if temp is not None and temp.exists():
            try: temp.unlink()
            except OSError: pass


def write_snapshot(path, payload):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    atomic_write_text(path,json.dumps(payload,ensure_ascii=False))


def read_snapshot(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('version')!=1: raise ValueError('Neplatná verze zálohy.')
    for key in ('input','output','test','recipe_name','recipe_note'):
        if not isinstance(data.get(key),str): raise ValueError('Neplatný text v záloze.')
    docs=data.get('documents')
    if not isinstance(docs,list): raise ValueError('Neplatný seznam souborů.')
    for doc in docs:
        if not isinstance(doc,dict) or not isinstance(doc.get('path'),str) or not isinstance(doc.get('text'),str):
            raise ValueError('Neplatný vstup v záloze.')
        if not isinstance(doc.get('excluded',[]),list) or any(type(i)!=int or i<0 for i in doc.get('excluded',[])):
            raise ValueError('Neplatný výběr kontur.')
    if type(data.get('document_index'))!=int or not 0<=data['document_index']<max(1,len(docs)):
        raise ValueError('Neplatný index vstupu.')
    if docs and docs[data['document_index']]['text'] != data['input']:
        raise ValueError('Text vybraného vstupu nesouhlasí s obnovovací kopií.')
    if not isinstance(data.get('settings'),dict) or any(type(v) not in (str,bool) for v in data['settings'].values()):
        raise ValueError('Neplatné nastavení.')
    return data
