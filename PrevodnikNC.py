"""PrevodnikNC desktop application, Python standard library only."""
from pathlib import Path
import math
import queue
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from tkinter import font as tkfont
from nc_core import parse_nc, export_nc, test_pattern, merge_drawings, NCError, fmt


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
    def __init__(self, master, title):
        super().__init__(master)
        self.drawing = None
        self.scale, self.ox, self.oy = 1, 60, 60
        self.pending = None
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        ttk.Label(bar, text=title, font=('Segoe UI', 10, 'bold')).pack(side='left', padx=5)
        ttk.Button(bar, text='Celý výkres', command=self.fit).pack(side='right')
        self.travel = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='Přejezdy', variable=self.travel, command=self.schedule).pack(side='right')
        self.canvas = tk.Canvas(self, background='#fafcfe', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.info = ttk.Label(self, text='Načtěte NC soubor.', padding=1)
        self.info.pack(fill='x')
        self.canvas.bind('<Configure>', lambda e: self.schedule())
        self.canvas.bind('<MouseWheel>', self.zoom)
        self.canvas.bind('<ButtonPress-1>', self.start_pan)
        self.canvas.bind('<B1-Motion>', self.pan)
        self.canvas.bind('<Double-Button-1>', lambda e: self.fit())

    def set_drawing(self, drawing):
        self.drawing = drawing
        if drawing:
            a, b, c, d = drawing.bounds()
            self.info.configure(text=f'Dráhy: {c-a:.3f} × {d-b:.3f} mm  |  X {a:.3f}…{c:.3f}  Y {b:.3f}…{d:.3f}')
        else:
            self.info.configure(text='Náhled není k dispozici.')
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
        if self.pending is not None: self.after_cancel(self.pending)
        self.pending = self.after(25, self.draw)

    def zoom(self, event):
        old = self.scale
        self.scale = min(100000, max(.001, old * (1.2 if event.delta > 0 else 1/1.2)))
        self.ox = event.x - (event.x-self.ox)*self.scale/old
        self.oy = event.y - (event.y-self.oy)*self.scale/old
        self.schedule()

    def start_pan(self, event):
        self.drag = event.x, event.y

    def pan(self, event):
        x, y = self.drag
        self.ox += event.x-x
        self.oy += event.y-y
        self.drag = event.x, event.y
        self.schedule()

    def draw(self):
        self.pending = None
        c = self.canvas
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if not self.drawing:
            c.create_text(w/2, h/2, text='Náhled drah v milimetrech', fill='#8492a6')
            return
        target = 75/self.scale
        base = 10**math.floor(math.log10(target))
        step = next(v*base for v in (1, 2, 5, 10) if v*base >= target)
        xmin, xmax = (45-self.ox)/self.scale, (w-self.ox)/self.scale
        ymin, ymax = (self.oy-h)/self.scale, (self.oy-28)/self.scale
        xticks, yticks = [], []
        for n in range(math.ceil(xmin/step), math.floor(xmax/step)+1):
            v = n*step; px = self.ox+v*self.scale
            xticks.append((px, v)); c.create_line(px, 28, px, h, fill='#e3e9ef')
        for n in range(math.ceil(ymin/step), math.floor(ymax/step)+1):
            v = n*step; py = self.oy-v*self.scale
            yticks.append((py, v)); c.create_line(45, py, w, py, fill='#e3e9ef')
        c.create_line(self.ox, 28, self.ox, h, fill='#bbc9d8')
        c.create_line(45, self.oy, w, self.oy, fill='#bbc9d8')
        for s in self.drawing.strokes:
            if not s.burn and not self.travel.get(): continue
            if len(s.points) < 2: continue
            # Whole polylines, split only for Tcl argument size. No skipped segments.
            for start in range(0, len(s.points)-1, 1500):
                points = s.points[start:start+1501]
                coords = [v for x, y in points for v in (self.ox+x*self.scale, self.oy-y*self.scale)]
                c.create_line(*coords, fill='#176b8a' if s.burn else '#c5cbd2', width=1)
        c.create_rectangle(0, 0, w, 28, fill='#eaf0f6', outline='')
        c.create_rectangle(0, 0, 45, h, fill='#eaf0f6', outline='')
        for px, v in xticks:
            c.create_line(px, 21, px, 28, fill='#61758a')
            c.create_text(px, 11, text=fmt(v), fill='#3c5369', font=('Segoe UI', 8))
        for py, v in yticks:
            c.create_line(38, py, 45, py, fill='#61758a')
            c.create_text(34, py, text=fmt(v), anchor='e', fill='#3c5369', font=('Segoe UI', 8))
        c.create_rectangle(0, 0, 45, 28, fill='#dce6f0', outline='')
        c.create_text(22, 14, text='mm', fill='#3c5369')


class App:
    def __init__(self, root):
        self.root = root
        root.title('PrevodnikNC • PCB → LaserGRBL')
        icon = Path(__file__).with_suffix('.ico')
        if icon.exists():
            try: root.iconbitmap(str(icon))
            except tk.TclError: pass
        root.geometry('1280x860'); root.minsize(960, 680)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 9))
        style.configure('TButton', padding=(6, 2))
        self.source = ''; self.path = None; self.output = ''; self.test_output = ''
        self.documents = []; self.document_index = 0
        self.dirty = {'input':False, 'output':False}
        self.output_path = None
        self.busy = False; self.jobs = queue.Queue(); self.revision = 0
        self.vars = {}
        self.status = tk.StringVar(value='Otevřete NC soubor. Kolečko: zoom • tažení: posun • dvojklik: celý výkres.')
        head = ttk.Frame(root, padding=(5,2)); head.pack(fill='x')
        ttk.Label(head, text='PrevodnikNC', font=('Segoe UI', 12, 'bold')).pack(side='left')
        ttk.Label(head, text='PCB / laserový převodník', foreground='#61758a').pack(side='left', padx=20)
        notebook = ttk.Notebook(root); notebook.pack(fill='both', expand=True, padx=4)
        convert = ttk.Frame(notebook, padding=3); test = ttk.Frame(notebook, padding=3)
        notebook.add(convert, text='  Převod NC  '); notebook.add(test, text='  Test výkonu a rychlosti  ')
        toolbar = ttk.Frame(convert); toolbar.pack(fill='x')
        ttk.Button(toolbar, text='Otevřít NC…', command=self.open_file).pack(side='left')
        ttk.Button(toolbar, text='Přidat soubor…', command=lambda:self.open_file(add=True)).pack(side='left',padx=3)
        self.document_choice = ttk.Combobox(toolbar,state='readonly',width=25)
        self.document_choice.pack(side='left')
        self.document_choice.bind('<<ComboboxSelected>>',self.select_document)
        ttk.Button(toolbar,text='Odebrat',command=self.remove_document).pack(side='left',padx=3)
        self.filename = PathLabel(toolbar); self.filename.pack(side='left',fill='x',expand=True,padx=6)
        settings = ttk.LabelFrame(convert, text='Nastavení převodu', padding=3); settings.pack(fill='x', pady=3)
        self.entry(settings, 'feed', 'Rychlost [mm/min]', '2000', 0, 0)
        self.entry(settings, 'power', 'Výkon S', '', 0, 2)
        self.combo(settings, 'laser', 'Laser', ['M3', 'M4'], 'M3', 0, 4)
        self.combo(settings, 'mode', 'Pracovní dráhy', ['Automaticky', 'Podle Z', 'Podle M3/M5 a S'], 'Automaticky', 1, 0)
        self.entry(settings, 'threshold', 'Pracovní Z ≤ [mm]', '0', 1, 2)
        self.combo(settings, 'rotation', 'Otočit doleva', ['0°', '90°', '180°', '270°'], '0°', 1, 4)
        self.vars['mx'] = tk.BooleanVar(); self.vars['my'] = tk.BooleanVar()
        ttk.Checkbutton(settings, text='Obrátit X (vlevo ↔ vpravo)', variable=self.vars['mx']).grid(row=2,column=0,columnspan=2,sticky='w')
        ttk.Checkbutton(settings, text='Obrátit Y (dole ↔ nahoře)', variable=self.vars['my']).grid(row=2,column=2,columnspan=2,sticky='w')
        ttk.Label(settings, text='Otočení zachová levý dolní roh rozsahu drah.', foreground='#61758a').grid(row=2,column=4,columnspan=2,sticky='w')
        self.vars['holes'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings,text='Značit vrtací vpichy Z',variable=self.vars['holes']).grid(row=3,column=0,columnspan=2,sticky='w')
        self.entry(settings,'diameter','Průměr značky [mm]','0.3',3,2)
        ttk.Label(settings,text='Soubory se pálí v pořadí přidání.').grid(row=3,column=4,columnspan=2,sticky='w')
        actions = ttk.Frame(convert); actions.pack(fill='x', pady=(0,3))
        ttk.Button(actions, text='Konvert', command=self.convert).pack(side='left')
        self.save_button = ttk.Button(actions, text='Uložit NC…', command=lambda: self.save(False), state='disabled')
        self.save_button.pack(side='left', padx=8)
        ttk.Button(actions, text='Obnovit vstupní náhled', command=self.load_preview).pack(side='left')
        self.views = ttk.Notebook(convert); self.views.pack(fill='both', expand=True)
        both = ttk.Panedwindow(self.views, orient='horizontal'); self.views.add(both,text='  Před a po převodu  ')
        self.before = Preview(both, 'Vstupní NC'); self.after = Preview(both, 'Výstup pro LaserGRBL')
        both.add(self.before, weight=1); both.add(self.after, weight=1)
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
        self.log.pack(fill='x', pady=(2,0))
        self.build_test(test)
        ttk.Label(root, textvariable=self.status, padding=2).pack(fill='x')
        for key in ('feed','power','laser','mode','threshold','mx','my','rotation','holes','diameter'):
            self.vars[key].trace_add('write', lambda *args: self.invalidate(False))
        root.after(80, self.poll)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def entry(self, parent, key, title, default, row, col):
        self.vars[key] = tk.StringVar(value=default)
        ttk.Label(parent, text=title).grid(row=row,column=col,sticky='w',padx=(0,4),pady=1)
        ttk.Entry(parent,textvariable=self.vars[key],width=12).grid(row=row,column=col+1,sticky='w',padx=(0,12),pady=1)

    def combo(self, parent, key, title, choices, default, row, col):
        self.vars[key] = tk.StringVar(value=default)
        ttk.Label(parent,text=title).grid(row=row,column=col,sticky='w',padx=(0,4),pady=1)
        ttk.Combobox(parent,textvariable=self.vars[key],values=choices,state='readonly',width=20).grid(row=row,column=col+1,sticky='w',padx=(0,12),pady=1)

    def number(self, key):
        try:
            value = float(self.vars[key].get().replace(',', '.'))
            if not math.isfinite(value): raise ValueError()
            return value
        except ValueError:
            raise NCError(f'Pole „{key}“: zadejte platné číslo.')

    def mode(self):
        return {'Automaticky':'auto', 'Podle Z':'z', 'Podle M3/M5 a S':'spindle'}[self.vars['mode'].get()]

    def invalidate(self, test):
        self.revision += 1
        if test:
            self.test_output = ''; self.test_save.configure(state='disabled')
            self.test_preview.set_drawing(None); self.set_text(self.legend, '')
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
        if side == 'input' and self.documents: self.documents[self.document_index]['dirty'] = True
        self.update_editor_titles()
        preview = self.before if side == 'input' else self.after
        if preview.drawing: preview.set_drawing(None)
        if side == 'output': self.save_button.configure(state='normal')
        self.status.set('Text upraven — náhled obnovíte tlačítkem v editoru. Ukládá se přesný obsah editoru.')

    def allow_replace(self, sides):
        dirty = [s for s in sides if self.dirty[s]]
        if not dirty: return True
        names = ', '.join('vstup' if s == 'input' else 'výstup' for s in dirty)
        return messagebox.askyesno('Neuložené změny',f'Neuložený {names}. Pokračováním se tento text zahodí. Pokračovat?',default='no')

    def close(self):
        if self.allow_replace(('input','output')): self.root.destroy()

    def output_preview(self):
        if self.busy: return
        text = self.code.get('1.0','end-1c')
        if not text.strip(): return
        self.after.set_drawing(None)
        def done(drawing):
            self.after.set_drawing(drawing)
            self.set_text(self.log,self.report(drawing))
            self.status.set('Výstupní náhled obnoven podle upraveného textu.')
        self.run_job(lambda:parse_nc(text),done,error_editor=self.output_editor)

    @staticmethod
    def set_text(widget, text):
        widget.configure(state='normal'); widget.delete('1.0','end'); widget.insert('1.0',text); widget.configure(state='disabled')

    def run_job(self, job, done, error_editor=None):
        if self.busy:
            self.status.set('Právě zpracovávám předchozí úlohu…'); return
        self.busy = True; revision = self.revision
        self.error_editor = error_editor
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
                messagebox.showerror('Nelze zpracovat NC', str(error))
            else: done(result)
        except queue.Empty: pass
        self.root.after(80, self.poll)

    def sync_document(self):
        if self.documents:
            self.documents[self.document_index]['text'] = self.input_code.get('1.0','end-1c')

    def refresh_document_choices(self):
        self.document_choice['values'] = [f'{i+1}. {doc["path"].name}' for i,doc in enumerate(self.documents)]
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
        return [(str(doc['path']),doc['text']) for doc in self.documents] or [('Editor',self.input_code.get('1.0','end-1c'))]

    @staticmethod
    def parse_inputs(documents,mode,threshold,diameter):
        drawings = []
        for index,(name,text) in enumerate(documents):
            try: drawing = parse_nc(text,mode,threshold,drill_diameter=diameter)
            except NCError as error:
                raise NCErrorWithDocument(f'{name}\n{error}',index) from error
            drawing.warnings.insert(0,f'{index+1}. {name}: režim {drawing.mode}, vrtacích bodů {len(drawing.drill_points)}')
            drawings.append(drawing)
        return merge_drawings(drawings) if len(drawings)>1 else drawings[0]

    def open_file(self,add=False):
        if self.busy: return
        path = filedialog.askopenfilename(title='Otevřít NC', filetypes=[('NC / G-code','*.nc *.gcode *.tap *.ngc'),('Všechny soubory','*.*')])
        if not path: return
        if not add and not self.allow_replace(('input','output')): return
        try:
            try:
                source = Path(path).read_text(encoding='utf-8-sig')
            except UnicodeDecodeError:
                source = Path(path).read_text(encoding='cp1250')
        except (OSError, UnicodeError) as e:
            messagebox.showerror('Nelze otevřít',str(e)); return
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
        self.load_preview()

    def load_preview(self):
        if self.busy: return
        self.source = self.input_code.get('1.0','end-1c')
        if not self.source: return
        try:
            mode, threshold = self.mode(), self.number('threshold')
            diameter = self.number('diameter') if self.vars['holes'].get() else 0
        except NCError as e: messagebox.showerror('Nastavení',str(e)); return
        documents = self.input_snapshot()
        self.before.set_drawing(None)
        def done(drawing):
            self.before.set_drawing(drawing)
            self.set_text(self.log, self.report(drawing))
            self.status.set('Vstup načten. Nastavte výkon, rychlost a případné zrcadlení, pak Konvert.')
        self.run_job(lambda: self.parse_inputs(documents,mode,threshold,diameter), done,error_editor=self.input_editor)

    @staticmethod
    def report(drawing):
        count = sum(s.burn for s in drawing.strokes)
        return f'Režim vstupu: {drawing.mode} • pracovních drah: {count}\n' + '\n'.join(drawing.warnings)

    def convert(self):
        self.source = self.input_code.get('1.0','end-1c')
        if not self.source:
            messagebox.showinfo('Vstup','Nejdříve otevřete NC soubor.'); return
        if self.busy: return
        try:
            mode, threshold = self.mode(), self.number('threshold')
            feed, power = self.number('feed'), self.number('power')
            mx, my, laser = self.vars['mx'].get(), self.vars['my'].get(), self.vars['laser'].get()
            rotation = int(self.vars['rotation'].get().rstrip('°'))
            diameter = self.number('diameter') if self.vars['holes'].get() else 0
        except NCError as e: messagebox.showerror('Nastavení',str(e)); return
        if not self.allow_replace(('output',)): return
        self.invalidate(False)
        documents = self.input_snapshot()
        def job():
            drawing = self.parse_inputs(documents,mode,threshold,diameter)
            output = export_nc(drawing,feed,power,mx,my,laser,rotation=rotation)
            return drawing,output,parse_nc(output,'spindle')
        def done(result):
            drawing,self.output,outdrawing = result
            self.before.set_drawing(drawing); self.after.set_drawing(outdrawing)
            self.replace_editor('output',self.output,dirty=True); self.set_text(self.log,self.report(drawing))
            self.output_path = None; self.output_editor.path.set_path(None)
            self.save_button.configure(state='normal')
            self.status.set('Převedeno. Náhled vpravo je načten přímo z výsledného G-code. Soubor můžete uložit.')
        self.run_job(job,done,error_editor=self.input_editor)

    def save(self, test, source=False):
        output = self.test_output if test else (self.input_code if source else self.code).get('1.0','end-1c')
        if not output: return
        name = 'test_laseru.nc' if test else (self.path.name if source and self.path else
                self.output_path.name if not source and self.output_path else
                f'{self.documents[0]["path"].stem}_spojene_laser.nc' if len(self.documents)>1 and not source else
                f'{self.path.stem}_laser.nc' if self.path else 'novy.nc')
        path = filedialog.asksaveasfilename(title='Uložit NC',defaultextension='.nc',initialfile=name,
                                          initialdir=str(self.path.parent) if self.path else str(Path(__file__).parent),
                                          filetypes=[('NC soubor','*.nc'),('G-code','*.gcode')])
        if not path: return
        input_paths = [doc['path'].resolve() for doc in self.documents] or ([self.path.resolve()] if self.path else [])
        if not source and Path(path).resolve() in input_paths:
            messagebox.showerror('Vstupní soubor','Výsledek uložte pod jiným názvem než původní NC.'); return
        try:
            with Path(path).open('w',encoding='utf-8',newline='') as handle:
                handle.write(output)
        except OSError as e: messagebox.showerror('Uložení',str(e)); return
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
        settings = ttk.LabelFrame(parent,text='Plocha a testovací matice — souřadnice ve stejném pracovním systému jako PCB',padding=8)
        settings.pack(fill='x')
        fields = [('tx','Počátek X [mm]','0'),('ty','Počátek Y [mm]','0'),
                  ('tw','Šířka plochy [mm]','30'),('th','Výška plochy [mm]','20'),
                  ('cols','Sloupce (výkony)','3'),('rows','Řádky (rychlosti)','3'),
                  ('gap','Mezera polí [mm]','2'),('spacing','Rozteč čar [mm]','0.3'),
                  ('smin','Výkon S od',''),('smax','Výkon S do',''),
                  ('fmin','Rychlost od [mm/min]','1500'),('fmax','Rychlost do [mm/min]','2500')]
        for index,(key,title,default) in enumerate(fields):
            self.entry(settings,key,title,default,index//3,(index%3)*2)
        self.combo(settings,'tlaser','Laser',['M3','M4'],'M3',4,0)
        ttk.Label(settings,text='Sloupce zleva: rostoucí S. Řádky zdola: rostoucí F. Číslování je v legendě; text se nepálí.').grid(row=5,column=0,columnspan=6,sticky='w',pady=5)
        bar = ttk.Frame(parent); bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='Vytvořit test',command=self.generate_test).pack(side='left')
        self.test_save = ttk.Button(bar,text='Uložit test NC…',command=lambda:self.save(True),state='disabled'); self.test_save.pack(side='left',padx=8)
        self.test_preview = Preview(parent,'Testovací obrazec'); self.test_preview.pack(fill='both',expand=True)
        self.legend = ScrolledText(parent,height=4,wrap='word',state='disabled',font=('Consolas',9)); self.legend.pack(fill='x')
        for key,_,_ in fields:
            self.vars[key].trace_add('write',lambda *args:self.invalidate(True))
        self.vars['tlaser'].trace_add('write',lambda *args:self.invalidate(True))

    def generate_test(self):
        if self.busy: return
        try:
            keys = ['tx','ty','tw','th','cols','rows','gap','spacing','smin','smax','fmin','fmax']
            values = [self.number(k) for k in keys]
            for i in (4,5):
                if values[i] != int(values[i]): raise NCError('Počet řádků/sloupců musí být celé číslo.')
                values[i] = int(values[i])
            laser = self.vars['tlaser'].get()
        except NCError as e: messagebox.showerror('Nastavení testu',str(e)); return
        self.invalidate(True)
        def job():
            output,legend = test_pattern(*values,laser=laser)
            return output,legend,parse_nc(output,'spindle')
        def done(result):
            self.test_output,legend,drawing = result
            self.test_preview.set_drawing(drawing)
            self.set_text(self.legend,'\n'.join(legend))
            self.test_save.configure(state='normal')
            self.status.set('Test připraven k samostatnému uložení. X/Y určují umístění na volné ploše.')
        self.run_job(job,done)


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
