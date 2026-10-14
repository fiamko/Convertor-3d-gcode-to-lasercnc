"""Additional CNC UI; original laser generator remains separate."""
from pathlib import Path
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from nc_core import NCError, parse_nc, fmt, positive
from milling_core import export_mill, milling_test, preview_mill, milling_seconds, validate
from recovery import atomic_write_text


class MillingMixin:
    def build_milling(self, settings):
        self.vars['cnc']=tk.BooleanVar(value=False)
        self.mill_panel=ttk.Frame(self.convert_right,padding=4)
        self.mill_panel.pack(side='top',fill='x',before=self.convert_stats)
        ttk.Checkbutton(self.mill_panel,text='CNC frézka',variable=self.vars['cnc']).grid(row=0,column=0,sticky='w')
        self.mill_settings=ttk.Frame(self.mill_panel)
        self.mill_settings.grid(row=1,column=0,sticky='w')
        for i,(key,title,value) in enumerate([
            ('depth','Ponor (mm)','0.04'),('rpm','Otáčky (RPM)',''),
            ('plunge','Posuv Z (F)','60'),('safe','Přejezd Z (mm)','2'),('delay','Rozběh (s)','2'),('drill_extra','Vpich navíc (mm)','0.1')]):
            self.entry(self.mill_settings,key,title,value,i//2,2*(i%2))
            self.mill_settings.grid_slaves(row=i//2,column=2*(i%2)+1)[0].configure(width=8)
        self.laser_widgets=[settings.grid_slaves(row=0,column=c)[0] for c in (3,5)]
        self.hole_widgets=[settings.grid_slaves(row=3,column=c)[0] for c in (0,3)]
        self.vars['cnc'].trace_add('write',self.cnc_state)
        for key in ('cnc','depth','safe','plunge','rpm','delay','drill_extra'):
            self.vars[key].trace_add('write',lambda *a:self.invalidate(False))
        self.cnc_state()
        self.manual_selected=set(); self.manual_history=[]; self.manual_signature=None; self.output_path_map={}; self.output_map_text=''
        self.before.show_exclusions=False
        self.before.canvas.bind('<Button-1>',self.pick_path)
        self.before.canvas.bind('<Delete>',self.delete_paths)
        self.before.canvas.bind('<Control-z>',self.undo_paths)
        self.build_mill_test()

    def cnc_state(self,*args):
        if not hasattr(self,'mill_settings'): return
        cnc=self.vars['cnc'].get()
        if hasattr(self,'manual_selected'):
            self.before.set_drawing(None); self.manual_selected.clear()
        if cnc: self.mill_settings.grid()
        else: self.mill_settings.grid_remove()
        self.hole_widgets[1].configure(state='disabled' if cnc else 'normal')
        self.before.show_drills=cnc and self.vars['holes'].get()
        self.after.show_drills=cnc and self.vars['holes'].get()
        for widget in self.laser_widgets:
            widget.configure(state='disabled' if cnc else ('readonly' if isinstance(widget,ttk.Combobox) else 'normal'))

    def mill_values(self):
        values=[self.number(k) for k in ('feed','depth','safe','plunge','rpm','delay')]
        validate(*values)
        positive(self.number('drill_extra'),'Vpich navíc',zero=True)
        return values

    def build_mill_test(self):
        from PrevodnikNC import Preview,CodeEditor
        parent=ttk.Frame(self.notebook,padding=3)
        self.notebook.add(parent,text='  Test frézování  ')
        settings=ttk.Frame(parent); settings.pack(fill='x')
        settings.columnconfigure((0,1),weight=1,uniform='halves')
        panel=ttk.Frame(settings,padding=4,relief='groove',borderwidth=1)
        panel.grid(row=0,column=0,sticky='nsew',padx=(0,3))
        opts=ttk.Frame(settings,padding=4,relief='groove',borderwidth=1)
        opts.grid(row=0,column=1,sticky='nsew')
        fields=[('cx','Počátek X [mm]','0'),('cy','Počátek Y [mm]','0'),
            ('cw','Šířka plochy [mm]','20'),('ch','Výška plochy [mm]','12'),
            ('ccols','Sloupce (hloubky)','3'),('crows','Řádky (posuvy)','2'),
            ('cgap','Mezera polí [mm]','2'),('cspacing','Stopa / rozteč [mm]','0.2'),
            ('cdmin','Ponor od [mm]','0.02'),('cdmax','Ponor do [mm]','0.06'),
            ('cfmin','Posuv od [mm/min]','100'),('cfmax','Posuv do [mm/min]','200'),
            ]
        for i,(key,title,value) in enumerate(fields): self.entry(panel,key,title,value,i//2,2*(i%2))
        self.entry(opts,'ctraces','Šířky spojů [mm]','0,3; 0,5; 0,8; 1',0,0)
        self.combo(opts,'cborder','Obrysy pole',['0','1','2'],'0',1,0)
        self.entry(opts,'cbwidth','Stopa obrysu [mm]','0.2',2,0)
        self.entry(opts,'ccolgap','Mezera sloupečků [mm]','0.5',3,0)
        self.entry(opts,'csafe','Přejezd Z [mm]','2',1,2)
        self.entry(opts,'cplunge','Posuv Z [mm/min]','60',2,2)
        self.entry(opts,'crpm','Otáčky S [ot/min]','',3,2)
        for frame in (panel,opts):
            for widget in frame.winfo_children():
                widget.grid_configure(padx=(0,4))
                if isinstance(widget,(ttk.Entry,ttk.Combobox)): widget.configure(width=8)
        opts.grid_slaves(row=0,column=1)[0].configure(width=24)
        opts.grid_slaves(row=0,column=1)[0].grid_configure(columnspan=3)
        bar=ttk.Frame(parent); bar.pack(fill='x')
        ttk.Button(bar,text='Vytvořit test CNC',command=self.generate_mill_test).pack(side='left')
        self.mill_save=ttk.Button(bar,text='Uložit test CNC…',command=self.save_mill_test,state='disabled'); self.mill_save.pack(side='left',padx=8)
        self.mill_summary=tk.StringVar(value='Doplňte otáčky podle vřetena; ostatní hodnoty jsou návrh testovací matice.')
        book=ttk.Notebook(parent); book.pack(fill='both',expand=True)
        self.mill_preview=Preview(book,'',controls_parent=book,empty_message='',show_info=False); book.add(self.mill_preview,text='Náhled')
        self.mill_editor=CodeEditor(book,'Test CNC G-code',self.refresh_mill_test,self.save_mill_test); book.add(self.mill_editor,text='Editor G-code')
        self.dirty['mill']=False
        self.mill_editor.text.bind('<<Modified>>',self.mill_changed)
        for key,_,_ in fields:
            self.vars[key].trace_add('write',lambda *a:self.invalidate(True))
        for key in ('ctraces','cborder','cbwidth','ccolgap','csafe','cplunge','crpm'):
            self.vars[key].trace_add('write',lambda *a:self.invalidate(True))

    def mill_changed(self,event=None):
        if not self.mill_editor.text.edit_modified(): return
        self.mill_editor.text.edit_modified(False); self.dirty['mill']=True; self.revision+=1
        self.mill_editor.title.configure(text='Test CNC G-code • neuloženo')
        self.mill_preview.set_drawing(None); self.mill_save.configure(state='normal')
        self.mill_summary.set('Text změněn — obnovte náhled. Rozpis polí je v komentářích NC.')
        self.schedule_recovery()

    def generate_mill_test(self):
        if self.busy: return
        try:
            keys=('cx','cy','cw','ch','ccols','crows','cgap','cspacing','cdmin','cdmax','cfmin','cfmax','csafe','cplunge','crpm')
            values=[self.number(k) for k in keys]+[2.0]  # Fixed spindle spin-up, seconds.
            for i in (4,5):
                if values[i]!=int(values[i]): raise NCError('Počet polí musí být celé číslo.')
                values[i]=int(values[i])
            try: widths=[float(s.replace(',','.')) for s in re.split(r'[;\s]+',self.vars['ctraces'].get().strip()) if s]
            except ValueError: raise NCError('Šířky spojů oddělte středníkem.')
            if not widths: raise NCError('Vyplňte šířky spojů.')
            options=dict(trace_widths=widths,border_count=int(self.vars['cborder'].get()),
                         border_width=self.number('cbwidth'),compare_widths=True,column_gap=self.number('ccolgap'))
        except (NCError,ValueError) as e:
            messagebox.showerror('Test CNC',str(e)); return
        if not self.allow_replace(('mill',)): return
        def job():
            text,legend=milling_test(*values,**options)
            return text,legend,preview_mill(text)
        def done(result):
            text,legend,drawing=result
            self.set_mill_text(text,True)
            self.mill_preview.set_drawing(drawing)
            self.mill_summary.set(('Šířky zleva [mm]: '+' / '.join(fmt(w) for w in widths)+'; měď / odebraná plocha 1:1. | ')+' | '.join(legend)+' | '+self.mill_time(text))
            self.save_recovery()
            self.status.set('Test CNC připraven. Před uložením zkontrolujte polohu X/Y a velikost na volném místě desky.')
        self.run_job(job,done)

    def set_mill_text(self,text,dirty):
        self.mill_editor.text.delete('1.0','end'); self.mill_editor.text.insert('1.0',text)
        self.mill_editor.text.edit_reset(); self.mill_editor.text.edit_modified(False)
        self.dirty['mill']=dirty; self.mill_editor.path.set_path(None)
        self.mill_editor.title.configure(text='Test CNC G-code'+(' • neuloženo' if dirty else ''))
        self.mill_save.configure(state='normal' if text else 'disabled')

    def mill_time(self,text):
        try:
            seconds=round(milling_seconds(text,self.number('rapid')))
            return f'Odhad XYZ + rozběh {seconds//60}:{seconds%60:02d} (bez akcelerace, pauz a prvního příjezdu; G0 dle nastavení).'
        except NCError: return 'Odhad času vyžaduje kladný G0 v záložce Převod NC.'

    def refresh_mill_test(self):
        if self.busy: return
        text=self.mill_editor.text.get('1.0','end-1c')
        def done(d):
            self.mill_preview.set_drawing(d); self.mill_summary.set(self.mill_time(text))
        self.run_job(lambda:preview_mill(text),done)

    def save_mill_test(self):
        text=self.mill_editor.text.get('1.0','end-1c')
        if not text.strip(): return
        path=filedialog.asksaveasfilename(title='Uložit test frézování',initialdir=self.last_directory or None,
            initialfile='test_frezovani.nc',defaultextension='.nc',filetypes=[('NC','*.nc')])
        if not path: return
        if any(Path(path).resolve()==d['path'].resolve() for d in self.documents):
            messagebox.showerror('Vstup','Test nelze uložit přes vstupní NC.'); return
        try: atomic_write_text(path,text)
        except OSError as e: messagebox.showerror('Uložení',str(e)); return
        self.last_directory=str(Path(path).parent); self.schedule_preferences()
        self.dirty['mill']=False; self.mill_editor.path.set_path(path)
        self.mill_editor.title.configure(text='Test CNC G-code'); self.status.set(f'Uloženo: {path}')

    def mark_input_paths(self):
        self.manual_selected=set(); self.manual_map=[]
        self.manual_signature=(self.input_snapshot(),self.mode(),self.number('threshold'),self.vars['holes'].get(),self.vars['diameter'].get(),self.vars['cnc'].get())
        excluded=set(); offset=0
        for doc_index,doc in enumerate(self.manual_signature[0]):
            drawing=parse_nc(doc[1],self.mode(),self.number('threshold'),
                self.number('diameter') if self.vars['holes'].get() and not self.vars['cnc'].get() else 0)
            self.manual_map.extend((doc_index,i) for i in range(len(drawing.strokes)))
            excluded.update(offset+i for i in (doc[2] if len(doc)>2 else [])); offset+=len(drawing.strokes)
        self.before.highlight_ids=set(); self.before.excluded_indices=excluded; self.before.schedule()

    def pick_path(self,event):
        if self.busy or not self.before.drawing: return
        canvas=self.before.canvas; canvas.focus_set()
        if not event.state & 4: self.manual_selected.clear()
        found=self.before.hit_stroke(event.x,event.y)
        if found is not None:
            if found in self.manual_selected: self.manual_selected.remove(found)
            else: self.manual_selected.add(found)
            self.highlight_path_text(found)
        self.before.highlight_ids={id(self.before.drawing.strokes[i]) for i in self.manual_selected}
        self.before.schedule()
        self.status.set(f'Vybráno {len(self.manual_selected)} drah. Delete vyřadí, Ctrl+Z vrátí poslední ruční změnu.')

    def delete_paths(self,event=None):
        if self.busy or not self.before.drawing or not self.manual_selected: return 'break'
        now=(self.input_snapshot(),self.mode(),self.number('threshold'),self.vars['holes'].get(),self.vars['diameter'].get(),self.vars['cnc'].get())
        if now!=self.manual_signature:
            self.status.set('Vstup se změnil — obnovte náhled a vyberte dráhu znovu.'); return 'break'
        ready=False
        if not self.documents:
            self.documents=[dict(path=Path('editor.nc'),text=now[0][0][1],dirty=True)]; self.document_index=0
        old=[list(d.get('excluded',[])) for d in self.documents]
        masks=[set(v) for v in old]
        for index in self.manual_selected:
            doc,stroke=self.manual_map[index]; masks[doc].add(stroke)
        if masks==[set(v) for v in old]: return 'break'
        # Leave at least one working path in each document, as existing contour logic requires.
        for di,mask in enumerate(masks):
            active=[i for i,s in enumerate(self.before.drawing.strokes) if self.manual_map[i][0]==di and s.burn]
            if active and all(self.manual_map[i][1] in mask for i in active):
                messagebox.showerror('Kontury','V jednom vstupu by nezůstala žádná pracovní dráha.'); return 'break'
        self.manual_history.append(([(str(d['path']),d['text']) for d in self.documents],self.mode(),self.number('threshold'),old))
        for d,mask in zip(self.documents,masks): d['excluded']=sorted(mask)
        self.manual_selected.clear(); self.revision+=1; self.refresh_document_choices(); self.save_recovery()
        self.stage_path_change()
        return 'break'

    def undo_paths(self,event=None):
        if self.busy or not self.manual_history: return 'break'
        signature,mode,threshold,old=self.manual_history[-1]
        self.sync_document()
        if signature!=[(str(d['path']),d['text']) for d in self.documents] or mode!=self.mode() or threshold!=self.number('threshold'):
            self.manual_history.clear(); self.status.set('Vstup se změnil; starý výběr nelze vrátit.'); return 'break'
        ready=False
        self.manual_history.pop()
        for d,mask in zip(self.documents,old): d['excluded']=mask
        self.revision+=1; self.refresh_document_choices(); self.save_recovery(); self.stage_path_change()
        return 'break'

    def stage_path_change(self):
        self.mark_input_paths()
        self.stats.set('Výběr drah změněn — výstupní text zůstává beze změn do Konvert.')
        self.status.set('Výběr k vyřazení uložen; vlevo zůstává originál. Ctrl+Z vrátí změnu; Konvert ji použije.')

    def capture_output_paths(self,drawing):
        self.output_map_text=self.code.get('1.0','end-1c')
        self.output_path_map={}
        kept=[i for i,s in enumerate(self.before.drawing.strokes)
              if s.burn and i not in self.before.excluded_indices]
        output=[s for s in drawing.strokes if s.burn]
        for index,stroke in zip(kept,output):
            doc,local=self.manual_map[index]
            source=self.manual_signature[0][doc]
            self.output_path_map[(source[0],source[1],local)]=stroke.source_lines

    def highlight_path_text(self,index):
        if index>=len(self.manual_map): return
        doc,local=self.manual_map[index]
        if self.documents and self.document_index!=doc: self.select_document(index=doc)
        lines=self.before.drawing.strokes[index].source_lines
        def highlight(widget,rows):
            widget.tag_configure('picked_path',background='#ffe4a3',foreground='#202020')
            widget.tag_remove('picked_path','1.0','end')
            for line in rows: widget.tag_add('picked_path',f'{line}.0',f'{line}.end+1c')
            if rows: widget.see(f'{rows[0]}.0'); widget.mark_set('insert',f'{rows[0]}.0')
        highlight(self.input_code,lines)
        source=self.manual_signature[0][doc]
        rows=self.output_path_map.get((source[0],source[1],local),[]) if self.code.get('1.0','end-1c')==self.output_map_text else []
        highlight(self.code,rows)

    def drill_notice(self,drawing):
        if self.vars['cnc'].get() and drawing.drill_points:
            count=len(drawing.drill_points)
            self.before.show_drills=self.vars['holes'].get()
            self.after.show_drills=self.vars['holes'].get()
            self.before.schedule(); self.after.schedule()
            if self.vars['holes'].get():
                self.status.set(f'Načteno {count} značkovacích bodů (fialové křížky). CNC vpichy: pracovní ponor + Vpich navíc; bez pohybu XY v materiálu.')
            else:
                self.status.set(f'Načteno {count} vrtacích bodů. Jejich značkování je vypnuté volbou Značit vrtací vpichy Z.')
