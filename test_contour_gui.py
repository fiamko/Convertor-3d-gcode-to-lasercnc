"""End-to-end contour editing and recovery, without a machine connection."""
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
import os
preferences_temp = tempfile.TemporaryDirectory()
os.environ["APPDATA"] = preferences_temp.name
from PrevodnikNC import App
from nc_core import export_nc,parse_nc
from test_contours import circles,HEADER
from recovery import read_snapshot

with tempfile.TemporaryDirectory() as temp:
    folder=Path(temp)
    root=tk.Tk(); root.withdraw(); app=App(root)
    app.recovery_folder=folder; app.recovery_path=folder/'recovery.json'
    app.vars['feed'].set('2600'); app.vars['power'].set('430')
    source=export_nc(circles(),1000,200)
    path=folder/'input.nc'; path.write_text(source)
    gerber=folder/'copper.gbr'
    gerber.write_text(HEADER+'%ADD10C,2*%\nD10*X0Y0D03*X1000000Y0D03*M02*')
    app.documents=[dict(path=path,text=source,dirty=False)]
    app.path=path; app.replace_editor('input',source); root.update()
    with patch.object(app,'run_job',side_effect=lambda job,done,error_editor=None,**kwargs:done(job())),patch('PrevodnikNC.messagebox.askyesno',return_value=True):
        with patch('PrevodnikNC.filedialog.askopenfilename',return_value=str(gerber)) as chooser:
            app.open_contours()
            chooser.assert_called_once()
        dialog=app.contour_dialog
        assert len(dialog.selected)==2
        dialog.count.set('2'); dialog.choose_layers(); assert len(dialog.selected)==4
        dialog.preview.draw()
        assert any(dialog.preview.canvas.gettags(i) and dialog.preview.canvas.itemcget(i,'fill')=='#da7800' for i in dialog.preview.canvas.find_all())
        dialog.commit_selection(); root.update()
        assert app.input_code.get('1.0','end-1c')==source
        assert path.read_text()==source
        assert sum(s.burn for s in parse_nc(app.code.get('1.0','end-1c')).strokes)==2
        assert sum(s.burn for s in app.before.drawing.strokes)==6
        app.load_preview()
        assert sum(s.burn for s in app.before.drawing.strokes)==6
        assert len(app.documents[0]['excluded'])==4
        saved=app.code.get('1.0','end-1c')
        snapshot=read_snapshot(app.recovery_path)
        assert snapshot['output']==saved and len(snapshot['documents'][0]['excluded'])==4
        backup=folder/'saved_session.json'; backup.write_bytes(app.recovery_path.read_bytes())
        app.restore_contours(); root.update()
        assert sum(s.burn for s in parse_nc(app.code.get('1.0','end-1c')).strokes)==6
        with patch('PrevodnikNC.filedialog.askopenfilename',return_value=str(backup)):
            app.restore_work()
        root.update()
        assert app.code.get('1.0','end-1c')==saved
        assert len(app.documents[0]['excluded'])==4
        app.convert(); root.update()
        assert sum(s.burn for s in parse_nc(app.code.get('1.0','end-1c')).strokes)==2
        with patch('PrevodnikNC.filedialog.asksaveasfilename',return_value=str(folder/'blocked.nc')),patch('PrevodnikNC.atomic_write_text',side_effect=PermissionError('blocked')),patch('PrevodnikNC.messagebox.showerror') as errors:
            app.save(False)
        assert errors.called
        assert app.code.get('1.0','end-1c')==saved
        assert app.dirty['output']
        app.output_editor.copy_all(); assert root.clipboard_get()==saved
        with patch('PrevodnikNC.write_snapshot',side_effect=PermissionError('blocked')):
            app.save_recovery()
        assert 'SELHALA' in app.recovery_status.get()
        # Same-name sibling Gerber opens without a file picker.
        sibling=folder/'input.gbr'; sibling.write_text(gerber.read_text())
        with patch('PrevodnikNC.filedialog.askopenfilename',side_effect=AssertionError('Unexpected picker')):
            app.open_contours()
        assert 'input.gbr' in app.contour_dialog.title()
        app.contour_dialog.destroy()
        # Multiple matching copper Gerbers require manual choice.
        (folder/'input.gbrl').write_text(gerber.read_text())
        with patch('PrevodnikNC.filedialog.askopenfilename',return_value='') as chooser:
            app.open_contours()
            chooser.assert_called_once()
        assert app.code.get('1.0','end-1c')==saved
        # Blank/invalid power must not prevent geometric selection or erase output.
        app.vars['contour_count'].set('1')
        for power in ('','abc','0','-1'):
            app.vars['power'].set(power)
            with patch('PrevodnikNC.filedialog.askopenfilename',return_value=str(gerber)),patch('PrevodnikNC.messagebox.showerror') as errors:
                app.open_contours()
                app.contour_dialog.commit_selection()
                root.update()
            assert not errors.called
            assert app.documents[0]['excluded']
            assert app.code.get('1.0','end-1c')==saved
            assert 'Výběr kontur je uložen' in app.status.get()
        app.vars['power'].set('')
        with patch('PrevodnikNC.messagebox.showerror') as errors:
            app.convert()
        assert 'Výkon S' in errors.call_args.args[1]
        app.vars['power'].set('430'); app.convert(); root.update()
        assert sum(s.burn for s in parse_nc(app.code.get('1.0','end-1c')).strokes)==4
        # Manual input changes invalidate its index-based selection.
        app.input_code.insert('1.0','; edited\n'); root.update()
        assert not app.documents[0].get('excluded')
    app.replace_editor('input','G0 Z5\nG0 X1 Y1\nG1 Z-1 F100\nG0 Z5\nM2')
    with patch('PrevodnikNC.filedialog.askopenfilename') as chooser,patch('PrevodnikNC.messagebox.showinfo') as info:
        app.open_contours()
        chooser.assert_not_called()
        assert 'vrtacích bodů' in info.call_args.args[1]
        assert 'se spoji' in info.call_args.args[1]
    root.destroy()
print('GUI contours OK: layer selection, preview, convert, undo selection, recover session, save failure and clipboard.')
