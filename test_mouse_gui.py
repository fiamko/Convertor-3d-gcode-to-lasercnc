"""Mouse editing and immediate panning regression checks; no machine connection."""
import os,tempfile,time,math
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch
from PrevodnikNC import App,Preview
from contour_ui import ContourDialog
from contour_tools import Copper
from nc_core import Drawing,Stroke

with tempfile.TemporaryDirectory() as folder:
 os.environ['APPDATA']=folder
 root=tk.Tk();app=App(root)
 drawing=Drawing(strokes=[Stroke([(0,0),(10,0)],True),Stroke([(0,5),(10,5)],True)])
 analysis=SimpleNamespace(selected=lambda count:{1},by_stroke={0:0,1:1},clearances={0:.1,1:.2},levels=[.1,.2],uncertain=[])
 dialog=ContourDialog(app,drawing,Copper([]),analysis,Preview,lambda *a:None)

 for _ in range(30): root.update();time.sleep(.01)
 preview=dialog.preview;c=preview.canvas
 x=round(preview.ox+5*preview.scale);y=round(preview.oy)
 view=(preview.scale,preview.ox,preview.oy)
 def double(x,y,t):
  for moment in (t,t+100):
   c.event_generate('<ButtonPress-1>',x=x,y=y,time=moment)
   c.event_generate('<ButtonRelease-1>',x=x,y=y,time=moment+20)
   root.update()
 with patch.object(preview,'fit',side_effect=AssertionError('Unexpected fit')):
  double(x,y,1000)
  assert 0 in dialog.selected and dialog.tree.set('0','remove')=='ANO'
  item=c.find_withtag('stroke:0')[0]
  assert c.itemcget(item,'fill')=='#cc2535' and c.itemcget(item,'dash')
  double(x,y,2000)
  assert 0 not in dialog.selected and dialog.tree.set('0','remove')=='—'
  assert c.itemcget(item,'fill')=='#176b8a' and not c.itemcget(item,'dash')
  double(2,2,3000)
  assert dialog.selected=={1}
 assert view==(preview.scale,preview.ox,preview.oy)
 dialog.select_path(SimpleNamespace(x=x,y=y));dialog.delete_selected()
 assert 0 in dialog.selected
 dialog.toggle_path(SimpleNamespace(x=x,y=y));assert 0 not in dialog.selected
 # Same canvas items move on the first motion, without a Python geometry rebuild.
 before=c.coords(item);original=tuple(drawing.strokes[0].points)
 with patch.object(preview,'draw',side_effect=AssertionError('Full redraw during pan')):
  preview.start_pan(SimpleNamespace(x=200,y=200))
  preview.pan(SimpleNamespace(x=217,y=209))
 assert item in c.find_withtag('stroke:0')
 assert c.coords(item)==[v+(17 if i%2==0 else 9) for i,v in enumerate(before)]
 assert preview.hit_stroke(x+17,y+9)==0
 assert tuple(drawing.strokes[0].points)==original
 preview.schedule();job=preview.pending
 for _ in range(20): preview.schedule()
 assert preview.pending==job
 dialog.destroy()
 # Representative dense geometry, including the copper background.
 window=tk.Toplevel(root);window.geometry('900x650')
 preview=Preview(window,'');preview.pack(fill='both',expand=True);root.update()
 dense=Drawing(strokes=[Stroke([(j*.01,i*.1+.01*math.sin(j)) for j in range(500)],True) for i in range(400)])
 preview.copper_polygons=[[(0,0),(5,0),(5,40),(0,40)]]
 preview.set_drawing(dense);
 for _ in range(30): root.update();time.sleep(.01)
 start=time.perf_counter();preview.draw();full=time.perf_counter()-start
 preview.start_pan(SimpleNamespace(x=200,y=200));start=time.perf_counter()
 preview.pan(SimpleNamespace(x=210,y=210));first=time.perf_counter()-start
 print(f'Mouse toggle OK; 200000 points: full redraw {full*1000:.1f} ms, first pan {first*1000:.1f} ms (handler time).')
 root.destroy()
