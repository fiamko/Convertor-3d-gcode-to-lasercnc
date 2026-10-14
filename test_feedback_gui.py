import os,tempfile,tkinter as tk
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from nc_core import parse_nc,export_nc,Drawing,Stroke
from contour_tools import ContourAnalysis,Copper
from contour_ui import ContourDialog
from test_feedback import DRILLS

with tempfile.TemporaryDirectory() as folder:
 os.environ['APPDATA']=folder
 from PrevodnikNC import App,Preview
 root=tk.Tk(); app=App(root); root.update()
 source=export_nc(Drawing(strokes=[Stroke([(0,0),(10,0)],True),Stroke([(0,.1),(10,.1)],True)]),100,200)
 app.documents=[dict(path=Path(folder)/'paths.nc',text=source,dirty=False)]
 app.replace_editor('input',source); app.vars['power'].set('200')
 with patch.object(app,'run_job',side_effect=lambda job,done,**kw:done(job())),patch('PrevodnikNC.messagebox.askyesno',return_value=True):
  app.convert(); root.update(); app.before.scale=20; app.before.ox=70; app.before.oy=160; app.before.draw()
  working=[i for i,s in enumerate(app.before.drawing.strokes) if s.burn]
  # Lines only two screen pixels apart: choose the nearest, not the last painted.
  app.before.canvas.event_generate('<Button-1>',x=150,y=160); root.update()
  assert app.manual_selected=={working[0]},app.manual_selected
  assert app.input_code.tag_ranges('picked_path')
  assert app.code.tag_ranges('picked_path')
  output=app.code.get('1.0','end-1c')
  app.before.canvas.focus_force(); app.before.canvas.event_generate('<Delete>'); root.update(); app.before.draw()
  assert app.code.get('1.0','end-1c')==output
  assert working[0] in app.before.excluded_indices
  assert all(app.before.canvas.itemcget(i,'fill')=='#176b8a' for i in app.before.canvas.find_withtag(f'stroke:{working[0]}'))
  app.convert(confirm=False); assert sum(s.burn for s in app.after.drawing.strokes)==1
  app.undo_paths(); app.convert(confirm=False); assert sum(s.burn for s in app.after.drawing.strokes)==2
  # Five nested levels: choose four, then plain click and Delete in modal preview.
  drawing=Drawing(strokes=[Stroke([(0,i),(10,i)],True) for i in range(5)])
  analysis=ContourAnalysis(list(range(5)),dict(enumerate(range(5))),[],dict(enumerate(range(5))))
  dialog=ContourDialog(app,drawing,Copper([]),analysis,Preview,lambda selected,d:None)
  dialog.count.set('4'); dialog.choose_layers(); assert dialog.selected=={0,1,2,3}
  dialog.count.set('1'); dialog.choose_layers(); root.update()
  dialog.preview.scale=30; dialog.preview.ox=70; dialog.preview.oy=220; dialog.preview.draw()
  dialog.preview.canvas.event_generate('<Button-1>',x=160,y=160); root.update()
  assert dialog.tree.selection()==('2',)
  assert 2 not in dialog.selected
  dialog.preview.canvas.focus_force(); dialog.preview.canvas.event_generate('<Delete>'); root.update()
  assert 2 in dialog.selected
  assert dialog.tree.item('2','values')[0]=='ANO'
  dialog.destroy()
  # Pure drill file must also export with no XY cutting.
  app.documents=[]; app.replace_editor('input',DRILLS)
  app.vars['cnc'].set(True); app.vars['rpm'].set('10000'); app.vars['drill_extra'].set('0.1')
  app.convert(confirm=False); root.update()
  cnc=app.code.get('1.0','end-1c')
  assert cnc.count('G1 Z-0.14 F60')==2
  assert app.after.show_drills and len(app.after.drawing.drill_points)==2
  assert 'G1 X' not in cnc
 root.destroy()
print('Feedback GUI OK: real click/Delete events, nearest path, input/output text, deferred conversion, four layers, CNC marking.')
