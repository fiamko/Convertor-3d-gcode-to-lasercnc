import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk
from test_milling import SOURCE
from nc_core import parse_nc
from milling_core import preview_mill
from recovery import read_snapshot

with tempfile.TemporaryDirectory() as folder:
    os.environ['APPDATA']=folder
    from PrevodnikNC import App
    root=tk.Tk(); root.withdraw(); app=App(root)
    assert app.recovery_folder.parent.name=='UpravaNC_Laser_CNC'
    app.vars['cnc'].set(True); app.vars['rpm'].set('10000'); app.vars['crpm'].set('10000')
    path=Path(folder)/'source.nc'; path.write_text(SOURCE)
    app.documents=[dict(path=path,text=SOURCE,dirty=False)]; app.path=path
    app.replace_editor('input',SOURCE)
    with patch.object(app,'run_job',side_effect=lambda job,done,**kw:done(job())), patch('PrevodnikNC.messagebox.askyesno',return_value=True):
        app.convert(); root.update()
        text=app.code.get('1.0','end-1c')
        assert '(CNC PCB' in text and 'M3 S10000' in text
        assert sum(s.burn for s in app.after.drawing.strokes)==2
        assert 'XYZ' in app.stats.get()
        app.output_preview(); assert sum(s.burn for s in app.after.drawing.strokes)==2
        app.before.draw()
        stroke=next(i for i,s in enumerate(app.before.drawing.strokes) if s.burn)
        points=app.before.drawing.strokes[stroke].points
        x=(points[0][0]+points[1][0])/2; y=(points[0][1]+points[1][1])/2
        app.pick_path(SimpleNamespace(x=app.before.ox+x*app.before.scale,y=app.before.oy-y*app.before.scale,state=0))
        assert app.manual_selected=={stroke}
        app.delete_paths(); root.update()
        assert app.code.get('1.0','end-1c')==text
        app.convert(confirm=False); root.update()
        assert len(app.documents[0]['excluded'])==1
        assert sum(s.burn for s in app.after.drawing.strokes)==1
        assert app.before.excluded_indices
        app.undo_paths(); root.update()
        app.convert(confirm=False); root.update()
        assert not app.documents[0]['excluded']
        assert sum(s.burn for s in app.after.drawing.strokes)==2
        assert path.read_text()==SOURCE
        app.generate_mill_test(); root.update()
        test=app.mill_editor.text.get('1.0','end-1c')
        assert test.count('M3 S10000')==1 and 'G1 Z-0.04' in test
        assert app.dirty['mill'] and app.mill_preview.drawing
        assert 'ccompare' not in app.vars and 'cpattern' not in app.vars and 'cdelay' not in app.vars
        assert 'G4 P2' in test
        assert 'Sloupecek 1: W 0.3 mm / mezera 0.3 mm' in test
        points=[s.points for s in app.mill_preview.drawing.strokes if s.burn]
        app.vars['ctraces'].set('0,4; 0,6; 0,9; 1,2')
        app.generate_mill_test(); root.update()
        test=app.mill_editor.text.get('1.0','end-1c')
        assert 'Sloupecek 1: W 0.4 mm / mezera 0.4 mm' in test
        assert points!=[s.points for s in app.mill_preview.drawing.strokes if s.burn]
        app.save_recovery(); snapshot=read_snapshot(app.recovery_path)
        assert snapshot['mill']==test
        saved=Path(folder)/'test_cnc.nc'
        with patch('milling_ui.filedialog.asksaveasfilename',return_value=str(saved)): app.save_mill_test()
        assert saved.read_text(encoding='utf-8')==test and not app.dirty['mill']
        backup=Path(folder)/'snapshot.json'; backup.write_bytes(app.recovery_path.read_bytes())
        app.set_mill_text('',False)
        with patch('PrevodnikNC.filedialog.askopenfilename',return_value=str(backup)): app.restore_work()
        assert app.mill_editor.text.get('1.0','end-1c')==test
        assert app.dirty['mill']
        app.vars['cnc'].set(False); app.vars['power'].set('400'); app.convert()
        assert '(CNC PCB' not in app.code.get('1.0','end-1c')
        assert 'G4 P' not in app.code.get('1.0','end-1c')
        app.vars['cnc'].set(True); app.recipe_name.set('CNC'); app.save_recipe()
        assert app.recipes['CNC']['rpm']=='10000'
        app.save_preferences()
        assert not (Path(folder)/'PrevodnikNC').exists()
    root.deiconify(); app.notebook.select(2); root.update()
    # Check rightmost controls fit at the default window width.
    for widget in app.mill_editor.winfo_toplevel().winfo_children(): pass
    def check_entries(w):
        for child in w.winfo_children():
            if child.winfo_ismapped() and child.winfo_class() in ('TEntry','TCombobox'):
                assert child.winfo_rootx()+child.winfo_width()<=root.winfo_rootx()+root.winfo_width(), str(child)
            check_entries(child)
    check_entries(root)
    print('CNC GUI OK: convert, picking, Delete/undo, matrix, save/recovery, independent profile, layout.')
    root.destroy()
