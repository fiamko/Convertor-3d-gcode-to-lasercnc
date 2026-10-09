"""Verify fitting after real Tk mapping, not just constructing hidden widgets."""
import os
import tempfile
import time
import tkinter as tk
from types import SimpleNamespace
from pathlib import Path
from PrevodnikNC import App, Preview
from contour_ui import ContourDialog
from contour_tools import parse_copper, analyze_contours
from test_contours import circles, HEADER
from nc_core import export_nc

with tempfile.TemporaryDirectory() as folder:
    os.environ['APPDATA']=folder
    root=tk.Tk(); root.withdraw(); app=App(root)
    def settle():
        until=time.monotonic()+.45
        while time.monotonic()<until:
            root.update(); time.sleep(.01)
    def fitted(preview):
        assert preview.canvas.winfo_ismapped()
        assert preview.canvas.winfo_width()>300
        assert not preview.initial_fit_pending
        auto=(preview.scale,preview.ox,preview.oy)
        preview.fit()
        assert auto==(preview.scale,preview.ox,preview.oy), (auto,(preview.scale,preview.ox,preview.oy))
    # Reproduce the old bug: data arrives while the viewport is still 1x1.
    window=tk.Toplevel(root); window.withdraw(); window.geometry('850x650')
    preview=Preview(window,'Test'); preview.pack(fill='both',expand=True)
    preview.set_drawing(circles()); window.deiconify(); settle(); fitted(preview)
    preview.zoom(SimpleNamespace(x=200,y=150,delta=120)); zoom=preview.scale
    window.geometry('900x680'); settle(); assert preview.scale==zoom
    window.destroy()
    root.deiconify(); settle()
    copper=parse_copper(HEADER+'%ADD10C,2*%\nD10*X0Y0D03*X1000000Y0D03*M02*')
    drawing=circles()
    dialog=ContourDialog(app,drawing,copper,analyze_contours(drawing,copper),Preview,lambda *a:None)
    settle(); assert dialog.state()=='normal'; fitted(dialog.preview); dialog.destroy()
    source=export_nc(drawing,1000,200)
    app.documents=[dict(path=Path(folder)/'source.nc',text=source,dirty=False)]
    app.replace_editor('input',source)
    failures=[]
    def check_candidate():
        dialog=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel))
        try:
            assert dialog.state()=='normal'
            fitted(next(w for w in dialog.winfo_children() if isinstance(w,Preview)))
        except Exception as exc: failures.append(exc)
        finally: dialog.destroy()
    root.after(450,check_candidate)
    assert not app.review_candidate(source)
    assert not failures, failures
    root.destroy()
print('Visible preview fit OK: delayed mapping, both dialogs, manual zoom preserved.')
