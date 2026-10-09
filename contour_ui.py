"""Review and adjust whole-contour selection before conversion."""
import tkinter as tk
from tkinter import ttk, messagebox
from contour_tools import copper_outlines


class ContourDialog(tk.Toplevel):
    def __init__(self, app, drawing, copper, analysis, preview_class, apply):
        super().__init__(app.root)
        self.title('Ubrat kontury nejblíž k mědi'); self.geometry('1120x780'); self.minsize(850,580)
        self.drawing=drawing; self.analysis=analysis; self.selected=set(); self.apply=apply
        top=ttk.Frame(self,padding=6); top.pack(fill='x')
        ttk.Label(top,text='Odebrat od mědi:').pack(side='left')
        self.count=app.vars['contour_count']
        choice=ttk.Combobox(top,textvariable=self.count,values=('1','2'),state='readonly',width=10)
        choice.pack(side='left',padx=5); choice.bind('<<ComboboxSelected>>',lambda e:self.choose_layers())
        ttk.Label(top,text='vrstvy   •   Oranžová = odebrat, modrá = ponechat, zelená = měď').pack(side='left')
        self.summary=tk.StringVar(); ttk.Label(self,textvariable=self.summary,padding=6).pack(fill='x')
        ttk.Label(self,text='Výběr je návrh podle vzdálenosti od Gerberu. Dvojklik v seznamu nebo Shift+klik na dráhu přepne její výběr.',padding=4).pack(fill='x')
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
        self.preview.canvas.bind('<Shift-Button-1>',self.toggle_path)
        bar=ttk.Frame(self,padding=6); bar.pack(fill='x')
        ttk.Button(bar,text='Zrušit',command=self.destroy).pack(side='right')
        self.commit=ttk.Button(bar,text='Použít výběr kontur',command=self.commit_selection)
        self.commit.pack(side='right',padx=6)
        ttk.Label(bar,text='Je-li vyplněn výkon S a rychlost, výběr se rovnou převede. Jinak je doplníte po zavření okna.').pack(side='left')
        self.choose_layers()
        self.transient(app.root); self.update_idletasks(); self.preview.viewport_ready(); self.grab_set()

    def choose_layers(self):
        self.selected=self.analysis.selected(int(self.count.get()))
        self.refresh()

    def refresh(self):
        focus=self.tree.selection()
        for iid in self.tree.get_children(): self.tree.delete(iid)
        number=0
        for index,stroke in enumerate(self.drawing.strokes):
            if not stroke.burn: continue
            number+=1
            level=self.analysis.by_stroke.get(index)
            distance=self.analysis.clearances.get(index)
            self.tree.insert('', 'end', iid=str(index),text=str(number),values=(
                'ANO' if index in self.selected else '—', 'ověřit' if level is None else level+1,
                '—' if distance is None else f'{distance:.4f}'))
        if focus and self.tree.exists(focus[0]): self.tree.selection_set(focus); self.tree.see(focus[0])
        self.preview.highlight_ids={id(self.drawing.strokes[i]) for i in self.selected}
        self.preview.schedule()
        total=sum(s.burn for s in self.drawing.strokes)
        levels=' / '.join(f'{v:.3f}' for v in self.analysis.levels)
        self.summary.set(f'Odstupy vrstev: {levels} mm  |  Odebrat: {len(self.selected)}  |  Zůstane: {total-len(self.selected)}  |  Nejednoznačné: {len(self.analysis.uncertain)} (automaticky ponechány)')
        self.commit.configure(state='normal' if 0<len(self.selected)<total else 'disabled')

    def toggle(self,index):
        if index in self.selected: self.selected.remove(index)
        else: self.selected.add(index)
        self.refresh()

    def toggle_row(self,event):
        row=self.tree.identify_row(event.y)
        if row: self.toggle(int(row))
        return 'break'

    def toggle_path(self,event):
        canvas=self.preview.canvas
        for item in reversed(canvas.find_overlapping(event.x-3,event.y-3,event.x+3,event.y+3)):
            for tag in canvas.gettags(item):
                if tag.startswith('stroke:'):
                    index=int(tag.split(':')[1])
                    if self.drawing.strokes[index].burn:
                        self.toggle(index); return 'break'
        return 'break'

    def commit_selection(self):
        if not self.selected: return
        self.apply(set(self.selected),self)
