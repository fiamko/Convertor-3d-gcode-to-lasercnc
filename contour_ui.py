"""Review and adjust whole-contour selection before conversion."""
import tkinter as tk
from tkinter import ttk, messagebox
from contour_tools import copper_outlines


class ContourDialog(tk.Toplevel):
    def __init__(self, app, drawing, copper, analysis, preview_class, apply, initial_selected=None):
        super().__init__(app.root)
        self.title('Ubrat kontury nejblíž k mědi'); self.geometry('1120x780'); self.minsize(850,580)
        self.focus_index=None
        self.drawing=drawing; self.analysis=analysis; self.selected=set(); self.apply=apply
        top=ttk.Frame(self,padding=6); top.pack(fill='x')
        ttk.Label(top,text='Odebrat od mědi:').pack(side='left')
        self.count=app.vars['contour_count']
        choice=ttk.Combobox(top,textvariable=self.count,values=('1','2','3','4'),state='readonly',width=10)
        choice.pack(side='left',padx=5); choice.bind('<<ComboboxSelected>>',lambda e:self.choose_layers())
        ttk.Label(top,text='vrstvy   •   Červená = odebrat, oranžová = vybraná, zelená = měď').pack(side='left')
        self.summary=tk.StringVar(); ttk.Label(self,textvariable=self.summary,padding=6).pack(fill='x')
        ttk.Label(self,text='Výběr je návrh podle vzdálenosti od Gerberu. Klik na čáru nebo řádek ji označí. Delete vyřadí; dvojklik na čáře nebo v seznamu přepne ponechat / odebrat.',padding=4).pack(fill='x')
        pane=ttk.Panedwindow(self,orient='horizontal'); pane.pack(fill='both',expand=True)
        self.preview=preview_class(pane,'Kontrola před odebráním')
        self.preview.copper_polygons=copper_outlines(copper)
        self.preview.set_drawing(drawing)
        pane.add(self.preview,weight=4)
        table=ttk.Frame(pane); pane.add(table,weight=1)
        self.tree=ttk.Treeview(table,columns=('remove','layer','distance'),show='tree headings',selectmode='browse',height=12)
        self.tree.heading('#0',text='Dráha'); self.tree.column('#0',width=55,stretch=False)
        for col,label,width in (('remove','Odebrat',62),('layer','Vrstva',62),('distance','Odstup mm',85)):
            self.tree.heading(col,text=label); self.tree.column(col,width=width,stretch=False)
        scroll=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Double-1>',self.toggle_row)
        self.preview.canvas.bind('<Button-1>',self.select_path)
        self.preview.canvas.bind('<Double-Button-1>',self.toggle_path)
        self.preview.canvas.bind('<Delete>',self.delete_selected)
        self.tree.bind('<<TreeviewSelect>>',self.select_row)
        self.tree.bind('<Delete>',self.delete_selected)
        bar=ttk.Frame(self,padding=6); bar.pack(fill='x')
        ttk.Button(bar,text='Zrušit',command=self.destroy).pack(side='right')
        self.commit=ttk.Button(bar,text='Použít a převést',command=self.commit_selection)
        self.commit.pack(side='right',padx=6)
        ttk.Label(bar,text='Použít a převést vytvoří výstup bez červených drah. Vstupní originál zůstává zachovaný.').pack(side='left')
        if initial_selected is None:
            self.choose_layers()
        else:
            self.selected={i for i in initial_selected if 0<=i<len(drawing.strokes) and drawing.strokes[i].burn}
            self.refresh()
        self.transient(app.root); self.update_idletasks(); self.preview.viewport_ready(); self.grab_set()

    def choose_layers(self):
        self.selected=self.analysis.selected(int(self.count.get()))
        self.refresh()

    def refresh(self):
        focus=self.tree.selection()
        number=0
        for index,stroke in enumerate(self.drawing.strokes):
            if not stroke.burn: continue
            number+=1
            level=self.analysis.by_stroke.get(index)
            distance=self.analysis.clearances.get(index)
            if not self.tree.exists(str(index)):
                self.tree.insert('', 'end', iid=str(index),text=str(number))
            self.tree.item(str(index),tags=('removed',) if index in self.selected else (),values=(
                'ANO' if index in self.selected else '—', 'ověřit' if level is None else level+1,
                '—' if distance is None else f'{distance:.4f}'))
        self.tree.tag_configure('removed',foreground='#cc2535')
        if focus and self.tree.exists(focus[0]): self.tree.see(focus[0])
        self.preview.excluded_indices=set(self.selected)
        self.preview.highlight_ids={id(self.drawing.strokes[self.focus_index])} if self.focus_index is not None else set()
        self.preview.refresh_styles()
        total=sum(s.burn for s in self.drawing.strokes)
        levels=' / '.join(f'{v:.3f}' for v in self.analysis.levels)
        self.summary.set(f'Odstupy vrstev: {levels} mm  |  Odebrat: {len(self.selected)}  |  Zůstane: {total-len(self.selected)}  |  Nejednoznačné: {len(self.analysis.uncertain)} (automaticky ponechány)')
        self.commit.configure(state='normal' if len(self.selected)<total else 'disabled')

    def toggle(self,index):
        if index in self.selected: self.selected.remove(index)
        else: self.selected.add(index)
        self.refresh()

    def toggle_row(self,event):
        row=self.tree.identify_row(event.y)
        if row: self.toggle(int(row))
        return 'break'

    def toggle_path(self,event):
        self.preview.canvas.focus_set()
        index=self.preview.hit_stroke(event.x,event.y)
        if index is not None:
            self.focus_index=None
            self.tree.selection_remove(self.tree.selection())
            self.toggle(index)
            self.tree.see(str(index))
        return 'break'

    def commit_selection(self):
        self.apply(set(self.selected),self)

    def select_row(self,event=None):
        rows=self.tree.selection()
        if not rows: return
        self.focus_index=int(rows[0])
        self.preview.highlight_ids={id(self.drawing.strokes[self.focus_index])}
        self.preview.refresh_styles()

    def select_path(self,event):
        self.preview.canvas.focus_set()
        index=self.preview.hit_stroke(event.x,event.y)
        if index is not None:
            self.focus_index=index
            self.tree.selection_set(str(index)); self.tree.see(str(index))
            self.select_row()
        return 'break'

    def delete_selected(self,event=None):
        if self.focus_index is not None:
            self.selected.add(self.focus_index); self.refresh()
        return 'break'
