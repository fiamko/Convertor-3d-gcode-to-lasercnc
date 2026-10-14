"""PrevodnikNC desktop application, Python standard library only."""
from pathlib import Path
import math
import json
import os
import sys
import queue
import re
import threading
from datetime import datetime
import uuid
from contour_tools import parse_copper, analyze_contours, omit_strokes, find_copper_file
from contour_ui import ContourDialog
from recovery import write_snapshot, read_snapshot, atomic_write_text
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from tkinter import font as tkfont
from nc_core import parse_nc, export_nc, test_pattern, merge_drawings, NCError, fmt, drawing_statistics, check_alignment


def output_filename(source, cnc=False):
    """Remove known CAM/export suffixes while retaining the project's own name."""
    name=Path(source).name if source else 'novy'
    suffix=re.compile(r'(?:[._-](?:spojene_laser|spojene_cnc|grb_drl|grb_cnc|B_Cu|F_Cu|NPTH|PTH|gcode|nc|gbrl|gbr|grb|gbl|gtl|drl|cnc|laser))$',re.I)
    while True:
        trimmed=suffix.sub('',name)
        if trimmed==name: break
        name=trimmed
    return f"{name or 'novy'}-grb_{'cnc' if cnc else 'drl'}.nc"


class NCErrorWithDocument(NCError):
    def __init__(self,message,index):
        super().__init__(message)
        self.document_index = index


class PathLabel(ttk.Label):
    """Keep the drive and longest fitting suffix; hover reveals the full path."""
    def __init__(self, parent):
        super().__init__(parent, text='Žádný soubor', width=1)
        self.full_path = ''; self.tip = None
        self.bind('<Configure>', lambda e: self.refresh())
        self.bind('<Enter>', self.show_tip)
        self.bind('<Leave>', self.hide_tip)

    def set_path(self, path):
        self.full_path = str(path) if path else ''
        self.refresh()

    def refresh(self):
        text = self.full_path or 'Žádný soubor'
        font = tkfont.Font(font=ttk.Style().lookup('TLabel', 'font'))
        available = max(30, self.winfo_width()-8)
        if self.full_path and font.measure(text) > available:
            prefix = Path(self.full_path).anchor + '…'
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo+hi+1)//2
                candidate = prefix + text[-mid:]
                if font.measure(candidate) <= available: lo = mid
                else: hi = mid-1
            text = prefix + (text[-lo:] if lo else '')
        self.configure(text=text)

    def show_tip(self, event):
        if not self.full_path: return
        self.hide_tip()
        self.tip = tk.Toplevel(self); self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f'+{event.x_root+10}+{event.y_root+18}')
        ttk.Label(self.tip,text=self.full_path,padding=5).pack()

    def hide_tip(self, event=None):
        if self.tip: self.tip.destroy(); self.tip = None


class CodeEditor(ttk.Frame):
    def __init__(self, parent, title, refresh, save):
        super().__init__(parent)
        bar = ttk.Frame(self); bar.pack(fill='x')
        self.title = ttk.Label(bar,text=title,font=('Segoe UI',9,'bold')); self.title.pack(side='left')
        ttk.Button(bar,text='Uložit jako…',command=save).pack(side='right')
        ttk.Button(bar,text='Obnovit náhled',command=refresh).pack(side='right')
        ttk.Button(bar,text='Řádek…',command=self.ask_line).pack(side='right')
        ttk.Button(bar,text='Kopírovat vše',command=self.copy_all).pack(side='right')
        self.path = PathLabel(self); self.path.pack(fill='x',pady=2)
        area = ttk.Frame(self); area.pack(fill='both',expand=True)
        area.rowconfigure(0,weight=1); area.columnconfigure(1,weight=1)
        self.gutter = tk.Canvas(area,width=42,background='#eaf0f6',highlightthickness=0)
        self.gutter.grid(row=0,column=0,sticky='ns')
        self.number_job = None
        self.text = tk.Text(area,wrap='none',undo=True,maxundo=100,autoseparators=True,font=('Consolas',10))
        self.text.grid(row=0,column=1,sticky='nsew')
        sy = ttk.Scrollbar(area,orient='vertical',command=self.text.yview); sy.grid(row=0,column=2,sticky='ns')
        sx = ttk.Scrollbar(area,orient='horizontal',command=self.text.xview); sx.grid(row=1,column=1,sticky='ew')
        def scroll_changed(*args):
            sy.set(*args); self.schedule_numbers()
        self.text.configure(yscrollcommand=scroll_changed,xscrollcommand=sx.set)
        self.text.bind('<Control-a>',self.select_all)
        self.text.bind('<Control-g>',self.ask_line)
        for event in ('<Configure>','<Map>','<<Modified>>'):
            self.text.bind(event,self.schedule_numbers,add='+')
        self.text.tag_configure('error_line',background='#ffe2b8')

    def copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self.text.get('1.0','end-1c'))

    def schedule_numbers(self,event=None):
        if self.number_job is None:
            self.number_job = self.after_idle(self.draw_numbers)

    def draw_numbers(self):
        self.number_job = None
        self.gutter.delete('all')
        total = int(self.text.index('end-1c').split('.')[0])
        font = tkfont.Font(font=self.text['font'])
        width = max(38,font.measure('9'*len(str(total)))+14)
        if int(self.gutter['width']) != width: self.gutter.configure(width=width)
        index = self.text.index('@0,0')
        while True:
            info = self.text.dlineinfo(index)
            if info is None: break
            line = index.split('.')[0]
            self.gutter.create_text(width-7,info[1],anchor='ne',text=line,font=self.text['font'],fill='#61758a')
            index = self.text.index(f'{index} +1line linestart')
            if int(index.split('.')[0]) > total: break

    def goto_line(self,line,error=False):
        total = int(self.text.index('end-1c').split('.')[0])
        line = max(1,min(int(line),total))
        self.text.tag_remove('error_line','1.0','end')
        if error: self.text.tag_add('error_line',f'{line}.0',f'{line}.end+1c')
        self.text.mark_set('insert',f'{line}.0')
        self.text.see(f'{line}.0'); self.text.focus_set()
        self.schedule_numbers()

    def ask_line(self,event=None):
        total = int(self.text.index('end-1c').split('.')[0])
        line = simpledialog.askinteger('Přejít na řádek',f'Číslo řádku (1–{total}):',
                                      parent=self,minvalue=1,maxvalue=total)
        if line is not None: self.goto_line(line)
        return 'break'

    def select_all(self,event):
        self.text.tag_add('sel','1.0','end-1c'); return 'break'


class Preview(ttk.Frame):
    def __init__(self, master, title, controls_parent=None, empty_message="Načtěte NC soubor.", show_info=True):
        super().__init__(master)
        self.drawing = None
        self.scale, self.ox, self.oy = 1, 60, 60
        self.pending = None
        self.initial_fit_pending = False
        self.initial_fit_job = None
        bar = ttk.Frame(controls_parent if controls_parent is not None else self)
        if controls_parent is None:
            bar.pack(fill='x')
            ttk.Label(bar, text=title, font=('Segoe UI', 10, 'bold')).pack(side='left', padx=5)
        else:
            bar.place(relx=1, x=-4, y=0, anchor='ne')
        ttk.Button(bar, text='Celý výkres', command=self.fit).pack(side='right')
        self.travel = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='Přejezdy', variable=self.travel, command=self.schedule).pack(side='right')
        self.canvas = tk.Canvas(self, background='#fafcfe', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.empty_message=empty_message
        self.info = ttk.Label(self, text=empty_message, padding=1)
        if show_info: self.info.pack(fill='x')
        self.canvas.bind('<Configure>', self.viewport_ready)
        self.canvas.bind('<Map>', self.viewport_ready)
        self.canvas.bind('<MouseWheel>', self.zoom)
        self.canvas.bind('<ButtonPress-3>', self.start_pan)
        self.canvas.bind('<B3-Motion>', self.pan)
        self.canvas.bind('<Double-Button-1>', lambda e: self.fit())

    def set_drawing(self, drawing):
        self.drawing = drawing
        self.initial_fit_pending = bool(drawing)
        if drawing:
            a, b, c, d = drawing.bounds()
            self.info.configure(text=f'Dráhy: {c-a:.3f} × {d-b:.3f} mm  |  X {a:.3f}…{c:.3f}  Y {b:.3f}…{d:.3f}')
        else:
            self.info.configure(text=self.empty_message)
        self.fit()
        self.viewport_ready()

    def viewport_ready(self, event=None):
        self.schedule()
        if not self.initial_fit_pending: return
        if self.initial_fit_job is not None:
            self.after_cancel(self.initial_fit_job)
        self.initial_fit_job = self.after(120, self.fit_when_visible)

    def fit_when_visible(self):
        self.initial_fit_job = None
        if not self.canvas.winfo_ismapped() or min(self.canvas.winfo_width(),self.canvas.winfo_height()) <= 1:
            return  # Map/Configure will retry once the real viewport exists.
        self.initial_fit_pending = False
        self.fit()

    def fit(self):
        if self.drawing:
            a, b, c, d = self.drawing.bounds()
            w, h = max(200, self.canvas.winfo_width()), max(200, self.canvas.winfo_height())
            self.scale = min((w-100)/max(c-a, 1), (h-100)/max(d-b, 1))
            self.ox = (w+40)/2 - (a+c)/2*self.scale
            self.oy = (h+30)/2 + (b+d)/2*self.scale
        self.schedule()

    def schedule(self):
        if self.pending is None:
            self.pending = self.after(25, self.draw)

    def zoom(self, event):
        self.initial_fit_pending = False
        if self.initial_fit_job is not None:
            self.after_cancel(self.initial_fit_job); self.initial_fit_job = None
        old = self.scale
        self.scale = min(100000, max(.001, old * (1.2 if event.delta > 0 else 1/1.2)))
        self.ox = event.x - (event.x-self.ox)*self.scale/old
        self.oy = event.y - (event.y-self.oy)*self.scale/old
        self.schedule()

    def start_pan(self, event):
        self.initial_fit_pending = False
        if self.initial_fit_job is not None:
            self.after_cancel(self.initial_fit_job); self.initial_fit_job = None
        self.drag = event.x, event.y

    def pan(self, event):
        x, y = self.drag
        self.ox += event.x-x
        self.oy += event.y-y
        self.drag = event.x, event.y
        self.canvas.move('geometry',event.x-x,event.y-y)
        self.draw_guides()

    def hit_stroke(self,x,y,radius=7):
        if not self.drawing: return None
        ids=set()
        for item in self.canvas.find_overlapping(x-radius,y-radius,x+radius,y+radius):
            for tag in self.canvas.gettags(item):
                if tag.startswith('stroke:'): ids.add(int(tag.split(':')[1]))
        best=None; distance=radius*radius
        for index in sorted(ids):
            stroke=self.drawing.strokes[index]
            if not stroke.burn: continue
            for a,b in zip(stroke.points,stroke.points[1:]):
                ax,ay=self.ox+a[0]*self.scale,self.oy-a[1]*self.scale
                bx,by=self.ox+b[0]*self.scale,self.oy-b[1]*self.scale
                dx,dy=bx-ax,by-ay
                t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy))) if dx or dy else 0
                d=(x-ax-t*dx)**2+(y-ay-t*dy)**2
                if d<distance: best=index; distance=d
        return best

    def draw(self):
        self.pending = None
        c = self.canvas
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if not self.drawing:
            c.create_text(w/2, h/2, text='Náhled drah v milimetrech', fill='#8492a6')
            return
        for polygon in getattr(self,'copper_polygons',[]):
            coords=[v for x,y in polygon for v in (self.ox+x*self.scale,self.oy-y*self.scale)]
            c.create_polygon(*coords,fill='#d2e8cb',outline='',tags=('geometry',))
        excluded=getattr(self,'excluded_indices',set()) if getattr(self,'show_exclusions',True) else set()
        for stroke_index,s in enumerate(self.drawing.strokes):
            if not s.burn and not self.travel.get(): continue
            if len(s.points) < 2: continue
            # Whole polylines, split only for Tcl argument size. No skipped segments.
            for start in range(0, len(s.points)-1, 1500):
                points = s.points[start:start+1501]
                coords = [v for x, y in points for v in (self.ox+x*self.scale, self.oy-y*self.scale)]
                c.create_line(*coords, dash=(3,3) if stroke_index in excluded else (), fill=('#cc2535' if stroke_index in excluded else ('#da7800' if id(s) in getattr(self,'highlight_ids',set()) else '#176b8a')) if s.burn else '#c5cbd2', width=3 if id(s) in getattr(self,'highlight_ids',set()) else (2 if stroke_index in excluded else 1),tags=('geometry',f'stroke:{stroke_index}'))
        if getattr(self,'show_drills',False):
            for x,y in self.drawing.drill_points:
                px,py=self.ox+x*self.scale,self.oy-y*self.scale
                c.create_line(px-4,py,px+4,py,fill='#8d3d9c',width=2,tags=('geometry',))
                c.create_line(px,py-4,px,py+4,fill='#8d3d9c',width=2,tags=('geometry',))
        self.draw_guides()

    def refresh_styles(self):
        if not self.drawing: return
        if not self.canvas.find_withtag('geometry'):
            self.schedule(); return
        excluded=getattr(self,'excluded_indices',set()) if getattr(self,'show_exclusions',True) else set()
        highlighted=getattr(self,'highlight_ids',set())
        for index,stroke in enumerate(self.drawing.strokes):
            removed=index in excluded
            focused=id(stroke) in highlighted
            self.canvas.itemconfigure(f'stroke:{index}',
                dash=(3,3) if removed else (),
                fill=('#cc2535' if removed else '#da7800' if focused else '#176b8a') if stroke.burn else '#c5cbd2',
                width=3 if focused else 2 if removed else 1)

    def draw_guides(self):
        c=self.canvas
        c.delete('guides')
        w,h=c.winfo_width(),c.winfo_height()
        target = 75/self.scale
        base = 10**math.floor(math.log10(target))
        step = next(v*base for v in (1, 2, 5, 10) if v*base >= target)
        xmin, xmax = (45-self.ox)/self.scale, (w-self.ox)/self.scale
        ymin, ymax = (self.oy-h)/self.scale, (self.oy-28)/self.scale
        xticks, yticks = [], []
        for n in range(math.ceil(xmin/step), math.floor(xmax/step)+1):
            v = n*step; px = self.ox+v*self.scale
            xticks.append((px, v)); c.create_line(px, 28, px, h, fill='#e3e9ef',tags=('guides','grid'))
        for n in range(math.ceil(ymin/step), math.floor(ymax/step)+1):
            v = n*step; py = self.oy-v*self.scale
            yticks.append((py, v)); c.create_line(45, py, w, py, fill='#e3e9ef',tags=('guides','grid'))
        c.create_line(self.ox, 28, self.ox, h, fill='#bbc9d8',tags=('guides','grid'))
        c.create_line(45, self.oy, w, self.oy, fill='#bbc9d8',tags=('guides','grid'))
        c.create_rectangle(0, 0, w, 28, fill='#eaf0f6', outline='',tags=('guides',))
        c.create_rectangle(0, 0, 45, h, fill='#eaf0f6', outline='',tags=('guides',))
        for px, v in xticks:
            c.create_line(px, 21, px, 28, fill='#61758a',tags=('guides',))
            c.create_text(px, 11, text=fmt(v), fill='#3c5369', font=('Segoe UI', 8),tags=('guides',))
        for py, v in yticks:
            c.create_line(38, py, 45, py, fill='#61758a',tags=('guides',))
            c.create_text(34, py, text=fmt(v), anchor='e', fill='#3c5369', font=('Segoe UI', 8),tags=('guides',))
        c.create_rectangle(0, 0, 45, 28, fill='#dce6f0', outline='',tags=('guides',))
        c.create_text(22, 14, text='mm', fill='#3c5369',tags=('guides',))
        c.tag_lower('grid')



from milling_ui import MillingMixin
from milling_core import export_mill, preview_mill


class App(MillingMixin):
    def __init__(self, root):
        self.root = root
        root.title('Úprava NC • Laser a CNC • verze 0.6')
        icon = Path(__file__).with_suffix('.ico')
        if icon.exists():
            try: root.iconbitmap(str(icon))
            except tk.TclError: pass
        screen_w,screen_h=root.winfo_screenwidth(),root.winfo_screenheight()
        window_w,window_h=min(1280,screen_w-40),min(800,screen_h-100)
        root.geometry(f'{window_w}x{window_h}+10+10')
        root.minsize(min(960,window_w),min(600,window_h))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 9))
        style.configure('TButton', padding=(6, 2))
        self.source = ''; self.path = None; self.output = ''; self.test_output = ''
        self.documents = []; self.document_index = 0
        self.dirty = {'input':False, 'output':False, 'test':False}
        self.output_path = None
        self.busy = False; self.jobs = queue.Queue(); self.revision = 0
        self.vars = {}
        self.field_titles = {}
        self.choice_values = {}
        self.preferences_ready = False
        self.preferences_job = None
        self.last_directory = ""
        self.status = tk.StringVar(value='Otevřete NC soubor. Kolečko: zoom • tažení: posun • dvojklik: celý výkres.')
        head = ttk.Frame(root, padding=(5,2)); head.pack(fill='x')
        ttk.Label(head, text='PrevodnikNC', font=('Segoe UI', 12, 'bold')).pack(side='left')
        ttk.Label(head, text='PCB / laser a CNC • 0.5', foreground='#61758a').pack(side='left', padx=20)
        self.recovery_job = None
        self.recovery_folder = Path(os.environ.get('APPDATA',str(Path.home()))) / 'UpravaNC_Laser_CNC' / 'obnova'
        self.recovery_path = self.recovery_folder / (datetime.now().strftime('%Y%m%d-%H%M%S-')+uuid.uuid4().hex[:8]+'.json')
        self.recovery_status = tk.StringVar(value='Průběžná obnova připravena')
        ttk.Button(head,text='Obnovit práci…',command=self.restore_work).pack(side='right')
        ttk.Label(head,textvariable=self.recovery_status).pack(side='right',padx=8)
        self.build_recipes(root)
        notebook = ttk.Notebook(root); self.notebook = notebook; notebook.pack(fill='both', expand=True, padx=4)
        convert = ttk.Frame(notebook, padding=3); test = ttk.Frame(notebook, padding=3)
        notebook.add(convert, text='  Převod NC  '); notebook.add(test, text='  Test výkonu a rychlosti  ')
        top=ttk.Frame(convert); top.pack(fill='x')
        left=ttk.Frame(top); left.pack(side='left',fill='both',expand=True)
        self.convert_right=ttk.Frame(top); self.convert_right.pack(side='right',fill='both',padx=(8,0))
        toolbar = ttk.Frame(left); toolbar.pack(fill='x')
        ttk.Button(toolbar, text='Otevřít NC…', command=self.open_file).pack(side='left')
        ttk.Button(toolbar, text='Přidat soubor…', command=lambda:self.open_file(add=True)).pack(side='left',padx=3)
        ttk.Label(toolbar,text='Aktivní soubor:').pack(side='left',padx=(8,3))
        self.document_choice = ttk.Combobox(toolbar,state='readonly',width=10)
        self.document_choice.pack(side='left')
        self.document_choice.bind('<<ComboboxSelected>>',self.select_document)
        ttk.Button(toolbar,text='Odebrat',command=self.remove_document).pack(side='left',padx=3)
        self.filename = PathLabel(toolbar); self.filename.pack(side='left',fill='x',expand=True,padx=6)
        settings = ttk.Frame(left, padding=3); settings.pack(fill='x', pady=3)
        self.entry(settings, 'feed', 'Rychlost [mm/min]', '2000', 0, 0)
        self.entry(settings, 'power', 'Výkon S', '', 0, 2)
        self.combo(settings, 'laser', 'Laser', ['M3', 'M4'], 'M3', 0, 4)
        self.combo(settings, 'mode', 'Pracovní dráhy', ['Automaticky', 'Podle Z', 'Podle M3/M5 a S'], 'Automaticky', 1, 0)
        self.entry(settings, 'threshold', 'Pracovní Z ≤ [mm]', '0', 1, 2)
        self.combo(settings, 'rotation', 'Otočit doleva', ['0°', '90°', '180°', '270°'], '0°', 1, 4)
        self.vars['mx'] = tk.BooleanVar(); self.vars['my'] = tk.BooleanVar()
        ttk.Checkbutton(settings, text='Obrátit X (vlevo ↔ vpravo)', variable=self.vars['mx']).grid(row=2,column=0,columnspan=2,sticky='w')
        ttk.Checkbutton(settings, text='Obrátit Y (dole ↔ nahoře)', variable=self.vars['my']).grid(row=2,column=2,columnspan=2,sticky='w')
        ttk.Label(settings, text='Otočení zachová levý dolní roh rozsahu drah.', wraplength=190, foreground='#61758a').grid(row=2,column=4,columnspan=2,sticky='w')
        self.vars['holes'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings,text='Značit vrtací vpichy Z',variable=self.vars['holes']).grid(row=3,column=0,columnspan=2,sticky='w')
        self.entry(settings,'diameter','Průměr značky [mm]','0.3',3,2)
        ttk.Label(settings,text='CNC značky: svislý vpich, ponor + přídavek.',wraplength=190).grid(row=3,column=4,columnspan=2,sticky='w')
        actions = ttk.Frame(left); actions.pack(fill='x', pady=(0,3))
        ttk.Button(actions, text='Konvert', command=self.convert).pack(side='left')
        self.save_button = ttk.Button(actions, text='Uložit NC…', command=lambda: self.save(False), state='disabled')
        self.save_button.pack(side='left', padx=8)
        ttk.Button(actions, text='Obnovit vstupní náhled', command=self.load_preview).pack(side='left')
        ttk.Button(actions,text='Ubrat kontury…',command=self.open_contours).pack(side='left',padx=4)
        ttk.Button(actions,text='Vrátit kontury',command=self.restore_contours).pack(side='left')
        statsbar = ttk.Frame(self.convert_right,padding=4)
        self.convert_stats=statsbar
        statsbar.pack(side='bottom',fill='x',pady=(4,0))
        self.stats = tk.StringVar(value='Statistika: nejprve vytvořte výstup.')
        ttk.Label(statsbar,textvariable=self.stats,wraplength=390,justify='left').pack(anchor='w')
        rapidbar=ttk.Frame(statsbar); rapidbar.pack(anchor='w')
        ttk.Label(rapidbar,text='G0 [mm/min]:').pack(side='left')
        self.vars['rapid'] = tk.StringVar(value='3000')
        ttk.Entry(rapidbar,textvariable=self.vars['rapid'],width=12).pack(side='left')
        self.vars['rapid'].trace_add('write',lambda *a:self.update_statistics())
        ttk.Label(statsbar,text='* Ideální čas XY bez akcelerace, pauz a příjezdu z neznámé polohy. G0 podle stroje.',foreground='#61758a',wraplength=390,justify='left').pack(anchor='w')
        self.views = ttk.Notebook(convert); self.views.pack(fill='both', expand=True)
        both = ttk.Panedwindow(self.views, orient='horizontal'); self.views.add(both,text='  Před a po převodu  ')
        self.before = Preview(both, 'Vstupní NC',show_info=False); self.after = Preview(both, 'Výstupní NC (laser / CNC)',show_info=False)
        both.add(self.before, weight=1); both.add(self.after, weight=1)
        # Equal weights distribute only extra space; unequal requested widths
        # otherwise keep the input pane wider. Centre the divider on resize.
        both.bind('<Configure>',lambda event: both.sashpos(0,event.width//2))
        editors = ttk.Panedwindow(self.views,orient='horizontal')
        self.editors_tab = editors
        self.views.add(editors,text='  Editory G-code  ')
        self.input_editor = CodeEditor(editors,'Vstupní G-code',self.load_preview,lambda:self.save(False,source=True))
        self.output_editor = CodeEditor(editors,'Výstupní G-code',self.output_preview,lambda:self.save(False))
        editors.add(self.input_editor,weight=1); editors.add(self.output_editor,weight=1)
        self.input_code = self.input_editor.text; self.code = self.output_editor.text
        self.input_code.bind('<<Modified>>',lambda e:self.editor_changed('input'),add='+')
        self.code.bind('<<Modified>>',lambda e:self.editor_changed('output'),add='+')
        self.log = ScrolledText(convert, height=2, wrap='word', font=('Segoe UI', 8), state='disabled')
        self.build_test(test)
        self.build_milling(settings)
        for key in ('feed','power','laser','mode','threshold','mx','my','rotation','holes','diameter'):
            self.vars[key].trace_add('write', lambda *args: self.invalidate(False))
        for key in ('mode','threshold'):
            self.vars[key].trace_add('write',lambda *args:self.clear_contour_filters())
        root.after(80, self.poll)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.setup_preferences()
        root.bind('<F1>',self.show_help)

    def show_help(self,event=None):
        existing=getattr(self,'help_window',None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify(); existing.lift(); return 'break'
        dialog=tk.Toplevel(self.root); self.help_window=dialog
        dialog.title('PrevodnikNC 0.6 — Návod / Manual'); dialog.geometry('850x680')
        book=ttk.Notebook(dialog); book.pack(fill='both',expand=True)
        for label,name in [('Česky','docs/MANUAL_CS.md'),('English','docs/MANUAL_EN.md'),('Licence / License','LICENSE')]:
            page=ScrolledText(book,wrap='word',font=('Segoe UI',10),padx=12,pady=10)
            book.add(page,text=label)
            try: content=(Path(__file__).resolve().parent/name).read_text(encoding='utf-8')
            except OSError as exc: content=f'Návod nelze načíst / Cannot read manual: {exc}'
            page.insert('1.0',content); page.configure(state='disabled')
        dialog.bind('<Escape>',lambda event:dialog.destroy())
        return 'break'

    def setup_preferences(self):
        self.preferences_path = self.recovery_folder.parent / 'nastaveni.json'
        self.vars['contour_count'] = tk.StringVar(value='1')
        self.choice_values['contour_count'] = ('1','2','3','4')
        self.preference_vars = dict(self.vars)
        self.preference_vars.update(recipe_name=self.recipe_name, recipe_note=self.recipe_note)
        for name in ('before','after','test_preview','mill_preview'):
            self.preference_vars['travel_'+name] = getattr(self,name).travel
        try:
            data = json.loads(self.preferences_path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('version') != 1 or not isinstance(data.get('values'),dict):
                raise ValueError('Neplatný formát nastavení')
            for key,value in data['values'].items():
                var = self.preference_vars.get(key)
                if var is None: continue
                if isinstance(var,tk.BooleanVar):
                    if type(value) is not bool: continue
                elif not isinstance(value,str): continue
                if key in self.choice_values and value not in self.choice_values[key]: continue
                var.set(value)
            directory = data.get('directory','')
            if isinstance(directory,str) and Path(directory).is_dir(): self.last_directory=directory
            for key,book in (('tab',self.notebook),('view',self.views)):
                index=data.get(key)
                if type(index) is int and 0<=index<len(book.tabs()): book.select(index)
        except FileNotFoundError: pass
        except (OSError,ValueError,tk.TclError) as e:
            self.status.set(f'Poslední nastavení nelze načíst, použity výchozí hodnoty: {e}')
        self.preferences_ready = True
        for var in self.preference_vars.values(): var.trace_add('write',lambda *a:self.schedule_preferences())
        for book in (self.notebook,self.views): book.bind('<<NotebookTabChanged>>',lambda e:self.schedule_preferences(),add='+')

    def schedule_preferences(self):
        if not self.preferences_ready: return
        if self.preferences_job is not None: self.root.after_cancel(self.preferences_job)
        self.preferences_job=self.root.after(500,self.save_preferences)

    def save_preferences(self):
        if not self.preferences_ready: return
        if self.preferences_job is not None:
            self.root.after_cancel(self.preferences_job); self.preferences_job=None
        payload={'version':1,'values':{k:v.get() for k,v in self.preference_vars.items()},
                 'directory':self.last_directory,'tab':self.notebook.index('current'),'view':self.views.index('current')}
        try:
            self.preferences_path.parent.mkdir(parents=True,exist_ok=True)
            atomic_write_text(self.preferences_path,json.dumps(payload,ensure_ascii=False,indent=2))
        except OSError as e: self.status.set(f'Nastavení nelze uložit: {e}')

    def clear_contour_filters(self):
        had_selection=any(doc.get('excluded') for doc in self.documents)
        for doc in self.documents: doc.pop('excluded',None)
        if hasattr(self,'before'): self.before.set_drawing(None)
        if had_selection:
            self.refresh_document_choices()
            self.status.set('Změna režimu nebo hranice Z zrušila výběr kontur. Vyberte je znovu.')

    def open_contours(self):
        if self.busy: return
        text=self.input_code.get('1.0','end-1c')
        selected_document=self.document_index
        if not text.strip():
            messagebox.showinfo('Kontury','Nejdříve otevřete NC s izolačními konturami.'); return
        try:
            mode,threshold=self.mode(),self.number('threshold')
        except NCError as e:
            messagebox.showerror('Nastavení',str(e)); return
        nc_path=self.documents[selected_document]['path'] if self.documents else self.path
        try:
            drawing=parse_nc(text,mode,threshold)
        except NCError as e:
            messagebox.showerror('Kontury',str(e)); return
        if not any(stroke.burn for stroke in drawing.strokes):
            name=Path(nc_path).name if nc_path else 'Text v editoru'
            detail=(f'Obsahuje {len(drawing.drill_points)} vrtacích bodů, ale žádné pracovní kontury.'
                    if drawing.drill_points else 'Neobsahuje pracovní kontury v aktuálním režimu načítání.')
            messagebox.showinfo('Vyberte NC se spoji',
                f'Aktivní soubor: {name}\n{detail}\n\nV seznamu vedle tlačítka Přidat soubor vyberte NC se spoji (například B_Cu.gbrl.nc) a potom znovu použijte Ubrat kontury.'); return
        path=find_copper_file(nc_path)
        if path is None:
            path=filedialog.askopenfilename(title='Vyberte Gerber mědi — odpovídající soubor nebyl jednoznačně nalezen',
                initialdir=str(Path(nc_path).parent) if nc_path else str(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent),
                filetypes=[('Gerber mědi','*.gbr *.gbrl *.gbl *.gtl'),('Všechny soubory','*.*')])
        if not path: return
        self.last_directory=str(Path(path).parent)
        self.schedule_preferences()
        try: gerber=Path(path).read_text(encoding='utf-8-sig')
        except (OSError,UnicodeError) as e:
            messagebox.showerror('Gerber',str(e)); return
        cache_key=(text,mode,threshold,gerber)
        def job():
            cached=getattr(self,'contour_analysis_cache',None)
            if cached is not None and cached[0]==cache_key: return drawing,cached[1],cached[2]
            copper=parse_copper(gerber)
            return drawing,copper,analyze_contours(drawing,copper)
        def done(result):
            drawing,copper,analysis=result
            self.contour_analysis_cache=(cache_key,copper,analysis)
            if self.document_index!=selected_document or self.input_code.get('1.0','end-1c')!=text:
                self.status.set('Vstup se změnil — spusťte výběr kontur znovu.'); return
            def apply(selected,dialog):
                if self.document_index!=selected_document or self.input_code.get('1.0','end-1c')!=text:
                    dialog.destroy(); return
                ready=self.contour_conversion_ready()
                if ready and not self.allow_replace(('output',)): return
                self.sync_document()
                if not self.documents:
                    self.documents=[{'path':Path('editor.nc'),'text':text,'dirty':True}]
                    self.document_index=0; self.refresh_document_choices()
                self.manual_history.clear()
                self.documents[self.document_index]['excluded']=sorted(selected)
                self.refresh_document_choices()
                self.revision+=1
                self.save_recovery()
                dialog.destroy()
                if ready:
                    self.convert(confirm=False)
                else:
                    self.finish_contour_change(ready)
                    self.status.set('Výběr uložen, výstup zatím nevytvořen: doplňte platné parametry laseru/CNC a stiskněte Konvert.')
            saved_selection=self.documents[selected_document].get('excluded') if self.documents else None
            self.contour_dialog=ContourDialog(self,drawing,copper,analysis,Preview,apply,initial_selected=saved_selection)
            self.contour_dialog.title(f'Ubrat kontury — měď: {Path(path).name}')
            self.status.set(f'Měď: {path}. Červené kontury budou vyřazeny; tlačítko Použít a převést vytvoří výstup.')
        self.run_job(job,done,error_editor=self.input_editor,error_title='Nelze zpracovat kontury / Gerber')

    def restore_contours(self):
        if self.busy or not self.documents: return
        doc=self.documents[self.document_index]
        if not doc.get('excluded'):
            self.status.set('V tomto vstupu nejsou vyřazené kontury.'); return
        ready=self.contour_conversion_ready()
        self.manual_history.clear()
        doc.pop('excluded',None); self.revision+=1
        self.refresh_document_choices()
        self.save_recovery()
        self.finish_contour_change(ready)

    def contour_conversion_ready(self):
        try:
            if self.vars['cnc'].get():
                self.mill_values(); return True
            return self.number('feed')>0 and self.number('power')>0
        except NCError: return False

    def finish_contour_change(self, ready):
        self.stats.set('Výběr drah změněn — použijte Konvert. Dosavadní výstup zůstává zachován.')
        self.load_preview(status_text='Červené dráhy jsou vyřazené. Použijte Konvert pro nový výstup.')

    def schedule_recovery(self):
        if not hasattr(self,'recovery_path'): return
        if self.recovery_job is not None: self.root.after_cancel(self.recovery_job)
        self.recovery_job=self.root.after(1500,self.save_recovery)

    def save_recovery(self):
        if self.recovery_job is not None:
            self.root.after_cancel(self.recovery_job); self.recovery_job=None
        if not hasattr(self,'test_editor'): return
        self.sync_document()
        input_text=self.input_code.get('1.0','end-1c')
        output=self.code.get('1.0','end-1c'); test=self.test_editor.text.get('1.0','end-1c')
        if not (self.documents or input_text or output or test or self.mill_editor.text.get('1.0','end-1c')): return
        payload={'version':1,'documents':[{**doc,'path':str(doc['path'])} for doc in self.documents],
                 'document_index':self.document_index,'input':input_text,'output':output,'test':test,
                 'mill':self.mill_editor.text.get('1.0','end-1c'),
                 'settings':{key:var.get() for key,var in self.vars.items()},
                 'recipe_name':self.recipe_name.get(),'recipe_note':self.recipe_note.get()}
        try:
            write_snapshot(self.recovery_path,payload)
            self.recovery_status.set('Obnovovací kopie: '+datetime.now().strftime('%H:%M:%S'))
        except (OSError,ValueError) as e:
            self.recovery_status.set('ZÁLOHA SELHALA — použijte Kopírovat vše')
            self.status.set(f'Obnovovací kopii nelze uložit: {e}')

    def restore_work(self):
        if self.busy: return
        path=filedialog.askopenfilename(title='Obnovit práci — vyberte zálohu podle data a času',initialdir=str(self.recovery_folder),filetypes=[('Obnovovací kopie','*.json')])
        if not path: return
        self.last_directory=str(Path(path).parent)
        self.schedule_preferences()
        try:
            data=read_snapshot(path)
            # Validate settings before changing any editor.
            for key,value in data['settings'].items():
                if key not in self.vars: continue
                if isinstance(self.vars[key],tk.BooleanVar) and type(value)!=bool:
                    raise ValueError('Neplatná logická hodnota v záloze.')
                if isinstance(self.vars[key],tk.StringVar) and not isinstance(value,str):
                    raise ValueError('Neplatná textová hodnota v záloze.')
            if data['settings'].get('mode') not in ('Automaticky','Podle Z','Podle M3/M5 a S'):
                raise ValueError('Neplatný režim v záloze.')
        except (OSError,ValueError) as e:
            messagebox.showerror('Obnova',str(e)); return
        if not self.allow_replace(('input','output','test','mill')): return
        self.save_recovery()
        for key,value in data['settings'].items():
            if key in self.vars: self.vars[key].set(value)
        self.documents=[{**doc,'path':Path(doc['path']),'dirty':True} for doc in data['documents']]
        self.document_index=data['document_index']
        self.path=self.documents[self.document_index]['path'] if self.documents else None
        self.source=data['input']; self.output=data['output']; self.test_output=data['test']
        self.replace_editor('input',self.source,dirty=bool(self.source))
        self.replace_editor('output',self.output,dirty=bool(self.output))
        self.filename.set_path(self.path); self.input_editor.path.set_path(self.path)
        self.output_path=None; self.output_editor.path.set_path(None)
        self.test_editor.text.delete('1.0','end'); self.test_editor.text.insert('1.0',self.test_output)
        self.test_editor.text.edit_reset(); self.test_editor.text.edit_modified(False)
        self.dirty['test']=bool(self.test_output); self.test_editor.path.set_path(None)
        self.test_editor.title.configure(text='Testovací G-code • obnoveno')
        self.test_save.configure(state='normal' if self.test_output else 'disabled')
        self.set_mill_text(data.get('mill',''),bool(data.get('mill','')))
        self.manual_history.clear()
        self.recipe_name.set(data['recipe_name']); self.recipe_note.set(data['recipe_note'])
        self.refresh_document_choices()
        for preview in (self.before,self.after,self.test_preview,self.mill_preview): preview.set_drawing(None)
        self.stats.set('Obnovený text — obnovte náhled pro statistiku.')
        self.revision+=1; self.save_recovery()
        self.status.set('Práce obnovena včetně výběru kontur. Texty lze uložit nebo zkopírovat; náhledy obnovte tlačítkem.')

    RECIPE_KEYS = ('feed','power','laser','mode','threshold','mx','my','rotation','holes','diameter','rapid','cnc','depth','safe','plunge','rpm','delay','drill_extra')

    def build_recipes(self, parent):
        self.recipe_path = Path(os.environ.get('APPDATA', str(Path.home()))) / 'UpravaNC_Laser_CNC' / 'recepty.json'
        self.recipes = {}
        try:
            if self.recipe_path.exists():
                self.recipes = json.loads(self.recipe_path.read_text(encoding='utf-8'))
                if not isinstance(self.recipes,dict) or any(not isinstance(v,dict) for v in self.recipes.values()):
                    raise ValueError('Neplatný formát receptů')
        except (OSError,ValueError) as e:
            self.recipes = {}
            messagebox.showerror('Načtení receptů',str(e))
        bar = ttk.Frame(parent,padding=3); bar.pack(fill='x')
        ttk.Button(bar,text='Návod / F1',command=self.show_help).pack(side='right',padx=(4,0))
        ttk.Label(bar,text='Technologický recept:').pack(side='left')
        self.recipe_name = tk.StringVar()
        self.recipe_choice = ttk.Combobox(bar,textvariable=self.recipe_name,values=sorted(self.recipes),width=32)
        self.recipe_choice.pack(side='left',padx=4)
        self.recipe_choice.bind('<<ComboboxSelected>>',self.apply_recipe)
        ttk.Button(bar,text='Uložit recept',command=self.save_recipe).pack(side='left')
        ttk.Button(bar,text='Smazat',command=self.delete_recipe).pack(side='left')
        ttk.Label(bar,text=' Poznámka:').pack(side='left')
        self.recipe_note = tk.StringVar()
        ttk.Entry(bar,textvariable=self.recipe_note).pack(side='left',fill='x',expand=True)
        self.recipe_name.trace_add('write',lambda *args:self.schedule_recovery())
        self.recipe_note.trace_add('write',lambda *args:self.schedule_recovery())

    def persist_recipes(self, recipes):
        try:
            self.recipe_path.parent.mkdir(parents=True,exist_ok=True)
            temp = self.recipe_path.with_suffix('.tmp')
            temp.write_text(json.dumps(recipes,ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(self.recipe_path)
        except OSError as e:
            messagebox.showerror('Uložení receptů',str(e)); return False
        self.recipes = recipes
        self.recipe_choice['values'] = sorted(recipes)
        return True

    def save_recipe(self):
        name = self.recipe_name.get().strip()
        if not name:
            messagebox.showinfo('Recept','Napište název receptu do výběrového pole.'); return
        try:
            if self.vars['cnc'].get(): self.mill_values()
            for key in (('feed','diameter','rapid') if self.vars['cnc'].get() else ('feed','power','diameter','rapid')):
                if self.number(key) <= 0: raise NCError('Rychlosti, výkon a průměr musí být kladné.')
            self.number('threshold')
        except NCError as e:
            messagebox.showerror('Recept',str(e)); return
        if name in self.recipes and not messagebox.askyesno('Recept',f'Přepsat recept „{name}“?',default='no'): return
        recipes = dict(self.recipes)
        recipes[name] = {key:self.vars[key].get() for key in self.RECIPE_KEYS}
        recipes[name]['note'] = self.recipe_note.get()
        if self.persist_recipes(recipes): self.status.set(f'Recept uložen: {name}')

    def apply_recipe(self,event=None):
        recipe = self.recipes.get(self.recipe_name.get())
        if recipe is None: return
        for key in self.RECIPE_KEYS:
            if key in recipe: self.vars[key].set(recipe[key])
        self.recipe_note.set(recipe.get('note',''))
        self.status.set('Recept načten do polí. Použijte Konvert pro nový výstup.')

    def delete_recipe(self):
        name = self.recipe_name.get()
        if name not in self.recipes: return
        if not messagebox.askyesno('Recept',f'Smazat recept „{name}“?',default='no'): return
        recipes = dict(self.recipes); del recipes[name]
        if self.persist_recipes(recipes): self.recipe_name.set('')

    def update_statistics(self):
        if not hasattr(self,'after') or not self.after.drawing: return
        try:
            burn,travel,count,seconds = drawing_statistics(self.after.drawing,self.number('rapid'))
            duration = 'neznámý posuv' if seconds is None else f'{int(round(seconds))//60}:{int(round(seconds))%60:02d}'
            text=self.code.get('1.0','end-1c')
            if '(CNC PCB' in text:
                self.stats.set(f'Frézování: {burn/1000:.2f} m | Dráhy: {count} | '+self.mill_time(text))
            else:
                self.stats.set(f'Pálení: {burn/1000:.2f} m | Přejezdy: {travel/1000:.2f} m | Dráhy: {count} | Odhad: {duration}*')
        except NCError:
            self.stats.set('Pro odhad zadejte kladnou rychlost G0.')

    def test_changed(self,event=None):
        text = self.test_editor.text
        if not text.edit_modified(): return
        text.edit_modified(False)
        self.dirty['test'] = True; self.revision += 1
        self.schedule_recovery()
        self.test_editor.title.configure(text='Testovací G-code • neuloženo')
        self.test_preview.set_drawing(None)
        self.test_save.configure(state='normal')
        self.set_text(self.legend,'Text změněn — obnovte náhled. Rozpis je v komentářích G-kódu.')

    def refresh_test(self):
        if self.busy: return
        text = self.test_editor.text.get('1.0','end-1c')
        def done(drawing):
            self.test_preview.set_drawing(drawing)
            self.status.set('Náhled testu obnoven z editoru.')
        self.run_job(lambda:parse_nc(text),done)

    def review_candidate(self, source):
        try:
            base = self.parse_inputs(self.input_snapshot(),self.mode(),self.number('threshold'),0,apply_exclusions=False)
            candidate = parse_nc(source,self.mode(),self.number('threshold'),drill_diameter=self.number('diameter'))
            level, report = check_alignment(base,candidate)
        except (NCError,ValueError) as e:
            messagebox.showerror('Kontrola souboru',str(e)); return False
        dialog = tk.Toplevel(self.root); dialog.title('Kontrola před přidáním NC'); dialog.geometry('850x650')
        result = [False]
        colors = {'red':'#b3261e','amber':'#986500','gray':'#61758a'}
        ttk.Label(dialog,text=report,foreground=colors[level],wraplength=800,padding=8).pack(fill='x')
        ttk.Label(dialog,text='Modrá: stávající data. Oranžová: přidávaný soubor. Zkontrolujte polohy otvorů vůči spojům.').pack(fill='x')
        preview = Preview(dialog,'Společné souřadnice před transformací'); preview.pack(fill='both',expand=True)
        preview.highlight_ids = {id(s) for s in candidate.strokes}
        preview.set_drawing(merge_drawings([base,candidate]))
        def accept():
            result[0] = True; dialog.destroy()
        bar = ttk.Frame(dialog); bar.pack(fill='x')
        ttk.Button(bar,text='Přidat tento soubor',command=accept).pack(side='right',padx=8,pady=8)
        ttk.Button(bar,text='Zrušit — vybrat jiný',command=dialog.destroy).pack(side='right')
        dialog.transient(self.root); dialog.update_idletasks(); preview.viewport_ready(); dialog.grab_set(); self.root.wait_window(dialog)
        return result[0]

    def entry(self, parent, key, title, default, row, col):
        self.field_titles[key] = title
        self.vars[key] = tk.StringVar(value=default)
        ttk.Label(parent, text=title).grid(row=row,column=col,sticky='w',padx=(0,4),pady=1)
        ttk.Entry(parent,textvariable=self.vars[key],width=12).grid(row=row,column=col+1,sticky='w',padx=(0,12),pady=1)

    def combo(self, parent, key, title, choices, default, row, col):
        self.choice_values[key] = tuple(choices)
        self.vars[key] = tk.StringVar(value=default)
        ttk.Label(parent,text=title).grid(row=row,column=col,sticky='w',padx=(0,4),pady=1)
        ttk.Combobox(parent,textvariable=self.vars[key],values=choices,state='readonly',width=10).grid(row=row,column=col+1,sticky='w',padx=(0,12),pady=1)

    def number(self, key):
        try:
            value = float(self.vars[key].get().replace(',', '.'))
            if not math.isfinite(value): raise ValueError()
            return value
        except ValueError:
            raise NCError(f'Pole „{self.field_titles.get(key,key)}“: zadejte platné číslo.')

    def mode(self):
        return {'Automaticky':'auto', 'Podle Z':'z', 'Podle M3/M5 a S':'spindle'}[self.vars['mode'].get()]

    def invalidate(self, test):
        self.revision += 1
        self.schedule_recovery()
        if test:
            pass  # Keep the last generated/edited test until explicit regeneration.
        else:
            # Existing editor contents remain independent of converter settings.
            self.output = ''
        self.status.set('Nastavení změněno — projeví se při příštím převodu. Text editoru zůstává zachován.')

    def replace_editor(self, side, text, dirty=False):
        widget = self.input_code if side == 'input' else self.code
        widget.delete('1.0','end'); widget.insert('1.0',text)
        widget.edit_reset(); widget.edit_modified(False)
        widget.tag_remove('error_line','1.0','end')
        self.dirty[side] = dirty
        self.update_editor_titles()
        if side == 'output': self.save_button.configure(state='normal' if text else 'disabled')

    def update_editor_titles(self):
        for side,editor,title in (('input',self.input_editor,'Vstupní G-code'),('output',self.output_editor,'Výstupní G-code')):
            editor.title.configure(text=title + (' • neuloženo' if self.dirty[side] else ''))

    def editor_changed(self, side):
        widget = self.input_code if side == 'input' else self.code
        if not widget.edit_modified(): return
        widget.edit_modified(False)
        widget.tag_remove('error_line','1.0','end')
        self.dirty[side] = True; self.revision += 1
        if side == 'input' and self.documents:
            self.documents[self.document_index]['dirty'] = True
            self.documents[self.document_index].pop('excluded',None)
            self.refresh_document_choices()
        self.schedule_recovery()
        self.update_editor_titles()
        preview = self.before if side == 'input' else self.after
        if preview.drawing: preview.set_drawing(None)
        if side == 'output':
            self.save_button.configure(state='normal')
            self.stats.set('Statistika neaktuální — obnovte náhled výstupu.')
        self.status.set('Text upraven — náhled obnovíte tlačítkem v editoru. Ukládá se přesný obsah editoru.')

    def allow_replace(self, sides):
        dirty = [s for s in sides if self.dirty[s]]
        if not dirty: return True
        names = ', '.join({'input':'vstup','output':'výstup','test':'testovací G-code','mill':'test CNC'}[s] for s in dirty)
        return messagebox.askyesno('Neuložené změny',f'Neuložený {names}. Pokračováním se tento text zahodí. Pokračovat?',default='no')

    def close(self):
        if self.allow_replace(('input','output','test','mill')):
            self.save_recovery()
            self.save_preferences()
            self.root.destroy()

    def output_preview(self):
        if self.busy: return
        text = self.code.get('1.0','end-1c')
        if not text.strip(): return
        self.after.set_drawing(None)
        self.stats.set('Statistika: zpracovávám výstup…')
        def done(drawing):
            self.after.set_drawing(drawing)
            self.update_statistics()
            self.set_text(self.log,self.report(drawing))
            self.status.set('Výstupní náhled obnoven podle upraveného textu.')
        self.run_job(lambda:preview_mill(text) if '(CNC PCB' in text else parse_nc(text),done,error_editor=self.output_editor)

    @staticmethod
    def set_text(widget, text):
        widget.configure(state='normal'); widget.delete('1.0','end'); widget.insert('1.0',text); widget.configure(state='disabled')

    def run_job(self, job, done, error_editor=None, error_title='Nelze zpracovat NC'):
        if self.busy:
            self.status.set('Právě zpracovávám předchozí úlohu…'); return
        self.busy = True; revision = self.revision
        self.error_editor = error_editor
        self.error_title = error_title
        self.status.set('Zpracovávám soubor…')
        def work():
            try: self.jobs.put((done, job(), None, revision))
            except Exception as e: self.jobs.put((done, None, e, revision))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            done, result, error, revision = self.jobs.get_nowait()
            self.busy = False
            if revision != self.revision:
                self.status.set('Nastavení se během zpracování změnilo — spusťte akci znovu.')
            elif error:
                self.status.set('Zpracování se nezdařilo.')
                match = re.search(r'Řádek (\d+):',str(error))
                if match and self.error_editor:
                    if hasattr(error,'document_index'):
                        self.select_document(index=error.document_index)
                    self.views.select(self.editors_tab)
                    self.root.update_idletasks()
                    self.error_editor.goto_line(int(match[1]),error=True)
                messagebox.showerror(getattr(self,'error_title','Nelze zpracovat NC'), str(error))
            else: done(result)
        except queue.Empty: pass
        self.root.after(80, self.poll)

    def sync_document(self):
        if self.documents:
            self.documents[self.document_index]['text'] = self.input_code.get('1.0','end-1c')

    def refresh_document_choices(self):
        self.document_choice['values'] = [f'{i+1}. {doc["path"].name}' + (f' [−{len(doc["excluded"])} kontur]' if doc.get('excluded') else '') for i,doc in enumerate(self.documents)]
        if self.documents: self.document_choice.current(self.document_index)
        else: self.document_choice.set('')

    def select_document(self,event=None,index=None):
        self.sync_document()
        self.document_index = self.document_choice.current() if index is None else index
        if not self.documents: return
        doc = self.documents[self.document_index]
        self.path = doc['path']; self.source = doc['text']
        self.filename.set_path(self.path); self.input_editor.path.set_path(self.path)
        self.replace_editor('input',self.source,dirty=any(d['dirty'] for d in self.documents))
        self.refresh_document_choices()

    def remove_document(self):
        if self.busy or not self.documents: return
        self.sync_document()
        if self.documents[self.document_index]['dirty'] and not messagebox.askyesno('Neuložené změny','Odebrat tento vstup včetně neuložených úprav?',default='no'): return
        self.documents.pop(self.document_index)
        self.document_index = min(self.document_index,max(0,len(self.documents)-1))
        # Do not copy the removed editor into the newly selected document.
        if self.documents:
            self.replace_editor('input',self.documents[self.document_index]['text'])
            self.select_document(index=self.document_index)
        else:
            self.path = None; self.source = ''; self.replace_editor('input','')
            self.filename.set_path(None); self.input_editor.path.set_path(None)
            self.refresh_document_choices()
        self.invalidate(False); self.before.set_drawing(None)
        if self.documents: self.load_preview()

    def input_snapshot(self):
        self.sync_document()
        return [(str(doc['path']),doc['text'],doc.get('excluded',[])) for doc in self.documents] or [('Editor',self.input_code.get('1.0','end-1c'))]

    @staticmethod
    def parse_inputs(documents,mode,threshold,diameter,apply_exclusions=True):
        drawings = []
        for index,document in enumerate(documents):
            name,text = document[:2]
            excluded = document[2] if len(document)>2 else []
            try:
                drawing = parse_nc(text,mode,threshold,drill_diameter=diameter)
                if apply_exclusions and excluded: drawing = omit_strokes(drawing,excluded)
            except NCError as error:
                raise NCErrorWithDocument(f'{name}\n{error}',index) from error
            drawing.warnings.insert(0,f'{index+1}. {name}: režim {drawing.mode}, vrtacích bodů {len(drawing.drill_points)}')
            drawings.append(drawing)
        return merge_drawings(drawings) if len(drawings)>1 else drawings[0]

    def open_file(self,add=False):
        if self.busy: return
        path = filedialog.askopenfilename(title='Otevřít NC', initialdir=self.last_directory or None, filetypes=[('NC / G-code','*.nc *.gcode *.tap *.ngc'),('Všechny soubory','*.*')])
        if not path: return
        self.last_directory=str(Path(path).parent)
        self.schedule_preferences()
        if not add and not self.allow_replace(('input','output')): return
        try:
            try:
                source = Path(path).read_text(encoding='utf-8-sig')
            except UnicodeDecodeError:
                source = Path(path).read_text(encoding='cp1250')
        except (OSError, UnicodeError) as e:
            messagebox.showerror('Nelze otevřít',str(e)); return
        if add and self.documents and not self.review_candidate(source): return
        self.sync_document()
        if not add: self.documents = []
        self.documents.append({'path':Path(path),'text':source,'dirty':False})
        self.document_index = len(self.documents)-1
        self.path = Path(path); self.source = source
        self.filename.set_path(self.path)
        self.input_editor.path.set_path(self.path)
        self.replace_editor('input',source,dirty=any(d['dirty'] for d in self.documents))
        self.refresh_document_choices()
        if not add:
            self.output_path = None; self.output_editor.path.set_path(None)
            self.replace_editor('output','')
        self.invalidate(False); self.before.set_drawing(None); self.after.set_drawing(None)
        self.stats.set('Statistika neaktuální — vytvořte nebo obnovte výstup.')
        self.load_preview()

    def load_preview(self, status_text=None):
        if self.busy: return
        self.source = self.input_code.get('1.0','end-1c')
        if not self.source: return
        try:
            mode, threshold = self.mode(), self.number('threshold')
            diameter = self.number('diameter') if self.vars['holes'].get() and not self.vars['cnc'].get() else 0
        except NCError as e: messagebox.showerror('Nastavení',str(e)); return
        documents = self.input_snapshot()
        self.before.set_drawing(None)
        def done(drawing):
            self.before.set_drawing(drawing)
            self.mark_input_paths()
            self.set_text(self.log, self.report(drawing))
            self.status.set(status_text or 'Vstup načten. Nastavte technologii, parametry a případné zrcadlení, pak Konvert.')
            self.drill_notice(drawing)
        self.run_job(lambda: self.parse_inputs(documents,mode,threshold,diameter,apply_exclusions=False), done,error_editor=self.input_editor)

    @staticmethod
    def report(drawing):
        count = sum(s.burn for s in drawing.strokes)
        return f'Režim vstupu: {drawing.mode} • pracovních drah: {count}\n' + '\n'.join(drawing.warnings)

    def convert(self, confirm=True):
        self.source = self.input_code.get('1.0','end-1c')
        if not self.source:
            messagebox.showinfo('Vstup','Nejdříve otevřete NC soubor.'); return
        if self.busy: return
        try:
            mode, threshold = self.mode(), self.number('threshold')
            cnc=self.vars['cnc'].get()
            mill_values=self.mill_values() if cnc else None
            mark_drills=self.vars['holes'].get()
            drill_extra=self.number('drill_extra') if cnc else 0
            feed, power = self.number('feed'), (0 if cnc else self.number('power'))
            mx, my, laser = self.vars['mx'].get(), self.vars['my'].get(), self.vars['laser'].get()
            rotation = int(self.vars['rotation'].get().rstrip('°'))
            diameter = self.number('diameter') if self.vars['holes'].get() and not self.vars['cnc'].get() else 0
        except NCError as e: messagebox.showerror('Nastavení',str(e)); return
        if confirm and not self.allow_replace(('output',)): return
        self.invalidate(False)
        documents = self.input_snapshot()
        def job():
            drawing = self.parse_inputs(documents,mode,threshold,diameter)
            output = export_mill(drawing,*mill_values,mirror_x=mx,mirror_y=my,rotation=rotation,mark_drills=mark_drills,drill_extra=drill_extra) if cnc else export_nc(drawing,feed,power,mx,my,laser,rotation=rotation)
            original=self.parse_inputs(documents,mode,threshold,diameter,apply_exclusions=False)
            return original,output,(preview_mill(output) if cnc else parse_nc(output,'spindle'))
        def done(result):
            drawing,self.output,outdrawing = result
            self.before.set_drawing(drawing); self.after.set_drawing(outdrawing)
            self.mark_input_paths()
            self.update_statistics()
            self.replace_editor('output',self.output,dirty=True); self.capture_output_paths(outdrawing); self.update_statistics(); self.set_text(self.log,self.report(drawing))
            self.output_path = None; self.output_editor.path.set_path(None)
            self.save_button.configure(state='normal')
            self.save_recovery()
            self.status.set('Převedeno. Náhled vpravo je načten přímo z výsledného G-code. Soubor můžete uložit.')
            self.drill_notice(drawing)
        self.run_job(job,done,error_editor=self.input_editor)

    def save(self, test, source=False):
        output = self.test_editor.text.get('1.0','end-1c') if test else (self.input_code if source else self.code).get('1.0','end-1c')
        if not output: return
        if test: name='test_laseru.nc'
        elif source: name=self.path.name if self.path else 'novy.nc'
        elif self.output_path: name=self.output_path.name
        else:
            origin=self.documents[0]['path'] if self.documents else self.path
            name=output_filename(origin,cnc='(CNC PCB' in output)
        path = filedialog.asksaveasfilename(title='Uložit NC',defaultextension='.nc',initialfile=name,
                                          initialdir=self.last_directory or str(self.path.parent) if self.path else self.last_directory or str(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent),
                                          filetypes=[('NC soubor','*.nc'),('G-code','*.gcode')])
        if not path: return
        self.last_directory=str(Path(path).parent)
        self.schedule_preferences()
        input_paths = [doc['path'].resolve() for doc in self.documents] or ([self.path.resolve()] if self.path else [])
        if not source and Path(path).resolve() in input_paths:
            messagebox.showerror('Vstupní soubor','Výsledek uložte pod jiným názvem než původní NC.'); return
        try:
            atomic_write_text(path,output)
        except OSError as e:
            messagebox.showerror('Uložení',str(e)+'\n\nText zůstává v editoru. Použijte Kopírovat vše a vložte jej do Poznámkového bloku, nebo Uložit jako do jiné složky.'); return
        if test:
            self.dirty['test'] = False
            self.test_editor.path.set_path(path)
            self.test_editor.title.configure(text='Testovací G-code')
        if not test:
            side = 'input' if source else 'output'
            self.dirty[side] = False; self.update_editor_titles()
            if source:
                self.path = Path(path); self.filename.set_path(self.path); self.input_editor.path.set_path(self.path)
                self.source = output
                if self.documents:
                    self.documents[self.document_index].update(path=self.path,text=output,dirty=False)
                    self.dirty['input'] = any(d['dirty'] for d in self.documents)
                    self.update_editor_titles(); self.refresh_document_choices()
            else:
                self.output_path = Path(path); self.output_editor.path.set_path(self.output_path)
        self.status.set(f'Uloženo: {path}')

    def build_test(self, parent):
        settings = ttk.Frame(parent,padding=(3,2))
        settings.pack(fill='x')
        settings.columnconfigure((0,1),weight=1,uniform='halves')
        panel=ttk.Frame(settings,padding=4,relief='groove',borderwidth=1)
        panel.grid(row=0,column=0,sticky='nsew',padx=(0,3))
        options=ttk.Frame(settings,padding=4,relief='groove',borderwidth=1)
        options.grid(row=0,column=1,sticky='nsew')
        fields = [('tx','Počátek X [mm]','0'),('ty','Počátek Y [mm]','0'),
                  ('tw','Šířka plochy [mm]','30'),('th','Výška plochy [mm]','20'),
                  ('cols','Sloupce (výkony)','3'),('rows','Řádky (rychlosti)','3'),
                  ('gap','Mezera polí [mm]','2'),('spacing','Rozteč čar [mm]','0.2'),
                  ('smin','Výkon S od',''),('smax','Výkon S do',''),
                  ('fmin','Rychlost od [mm/min]','1500'),('fmax','Rychlost do [mm/min]','2500')]
        for index,(key,title,default) in enumerate(fields):
            self.entry(panel,key,title,default,index//2,(index%2)*2)
        self.entry(options,'trace_widths','Šířky spojů [mm]','0,3; 0,5; 0,8; 1',0,0)
        self.combo(options,'tborder','Obrysy pole',['0','1','2'],'2',1,0)
        self.entry(options,'tborder_width','Stopa obrysu [mm]','0.2',2,0)
        self.entry(options,'negative_gap','Mezera sloupečků [mm]','0.5',3,0)
        self.combo(options,'tlaser','Laser',['M3','M4'],'M3',1,2)
        self.vars['tnegative']=tk.BooleanVar(value=False)
        ttk.Checkbutton(options,text='Negativní rezist',variable=self.vars['tnegative']).grid(row=2,column=2,columnspan=2,sticky='w')
        for frame in (panel,options):
            for widget in frame.winfo_children():
                widget.grid_configure(padx=(0,4))
                if isinstance(widget,(ttk.Entry,ttk.Combobox)): widget.configure(width=8)
        options.grid_slaves(row=0,column=1)[0].configure(width=24)
        options.grid_slaves(row=0,column=1)[0].grid_configure(columnspan=3)
        bar = ttk.Frame(parent); bar.pack(fill='x',pady=3)
        ttk.Button(bar,text='Vytvořit test',command=self.generate_test).pack(side='left')
        self.test_save = ttk.Button(bar,text='Uložit test NC…',command=lambda:self.save(True),state='disabled'); self.test_save.pack(side='left',padx=8)
        self.test_views = ttk.Notebook(parent); self.test_views.pack(fill='both',expand=True)
        self.test_preview = Preview(self.test_views,'',controls_parent=self.test_views,empty_message='',show_info=False); self.test_views.add(self.test_preview,text='Náhled')
        self.test_editor = CodeEditor(self.test_views,'Testovací G-code',self.refresh_test,lambda:self.save(True))
        self.test_views.add(self.test_editor,text='Editor G-code')
        self.test_editor.text.bind('<<Modified>>',self.test_changed,add='+')
        self.legend = ScrolledText(parent,height=4,wrap='word',state='disabled',font=('Consolas',9))
        for key,_,_ in fields:
            self.vars[key].trace_add('write',lambda *args:self.invalidate(True))
        for key in ('tlaser','trace_widths','tborder','tborder_width','negative_gap','tnegative'):
            self.vars[key].trace_add('write',lambda *args:self.invalidate(True))

    def generate_test(self):
        if self.busy: return
        try:
            keys = ['tx','ty','tw','th','cols','rows','gap','spacing','smin','smax','fmin','fmax']
            values = [self.number(k) for k in keys]
            for i in (4,5):
                if values[i] != int(values[i]): raise NCError('Počet řádků/sloupců musí být celé číslo.')
                values[i] = int(values[i])
            laser = self.vars['tlaser'].get()
            negative=self.vars['tnegative'].get()
            border_count=self.number('tborder')
            negative_gap=self.number('negative_gap')
            if border_count not in (0,1,2): raise NCError('Počet obrysů musí být 0, 1 nebo 2.')
            border_count=int(border_count)
            border_width=self.number('tborder_width') if border_count else .2
            pass_mode = None
            try:
                trace_widths=[float(v.replace(',','.')) for v in re.split(r'[;\s]+',self.vars['trace_widths'].get().strip()) if v]
            except ValueError: raise NCError('Šířky spojů: zadejte čísla oddělená středníkem, například 0,3; 0,5; 0,8; 1.')
            if not trace_widths: raise NCError('Vyplňte alespoň jednu šířku spoje.')
        except NCError as e: messagebox.showerror('Nastavení testu',str(e)); return
        if not self.allow_replace(('test',)): return
        self.invalidate(True)
        def job():
            output,legend = test_pattern(*values,laser=laser,trace_widths=trace_widths,trace_pass_mode=pass_mode,border_count=border_count,border_width=border_width,negative=negative,negative_gap=negative_gap,comparison=True)
            return output,legend,parse_nc(output,'spindle')
        def done(result):
            self.test_output,legend,drawing = result
            self.test_editor.text.delete('1.0','end')
            self.test_editor.text.insert('1.0',self.test_output)
            self.test_editor.text.edit_reset(); self.test_editor.text.edit_modified(False)
            self.dirty['test'] = True
            self.test_editor.title.configure(text='Testovací G-code • neuloženo')
            self.test_editor.path.set_path(None)
            self.test_preview.set_drawing(drawing)
            note=('Spoje zleva [mm]: '+' / '.join(fmt(v) for v in trace_widths)+'\n') if trace_widths else ''
            if negative: note+='Negativní rezist: každá šířka má sloupeček; mezery = šířka. D '+fmt(values[7])+' mm; odstup D/2; krok '+fmt(.8*values[7])+' mm. Počty a polohy drah jsou v hlavičce NC.\n'
            if pass_mode: note+=f'Vzorky zleva: 1 / 2 / 3 dráhy; první odstup {fmt(values[7]/2)} mm; další krok {fmt(.8*values[7])} mm\n'
            if border_count: note+=f'Obrysy celého pole: {border_count}; šířka stopy {fmt(border_width)} mm; překrytí 20 %; rozteč {fmt(.8*border_width)} mm\n'
            self.set_text(self.legend,note+'\n'.join(legend))
            self.test_save.configure(state='normal')
            self.save_recovery()
            self.status.set('Test připraven k samostatnému uložení. Zadané rozměry plochy zůstaly zachovány.')
        self.run_job(job,done)


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
