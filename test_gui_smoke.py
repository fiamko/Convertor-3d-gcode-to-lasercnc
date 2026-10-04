"""Headless-in-spirit Tk smoke: initializes widgets and renders real reference paths."""
from pathlib import Path
import tkinter as tk
import tempfile
from unittest.mock import patch
from PrevodnikNC import App
from nc_core import parse_nc, export_nc, test_pattern

root = tk.Tk()
root.withdraw()
app = App(root)
root.update()
source = (Path(__file__).parent/'examples'/'obrys.nc').read_text(encoding='utf-8-sig')
drawing = parse_nc(source)
app.before.set_drawing(drawing)
app.after.set_drawing(parse_nc(export_nc(drawing,2000,800,True)))
app.test_preview.set_drawing(parse_nc(test_pattern(85,5,30,20,3,3,2,.3,200,500,1000,2000)[0]))
for preview in (app.before,app.after,app.test_preview):
    preview.draw()
    assert any(preview.canvas.type(item) == 'line' and preview.canvas.itemcget(item,'fill') == '#176b8a'
               for item in preview.canvas.find_all())
edited = '(Ruční úprava)\nG0 X0 Y0\nM4 S400\nG1 X9 Y2 F2000\nM5\nM2\n'
app.replace_editor('output',edited)
root.update()
assert not app.dirty['output']
app.code.insert('end-1c','; poznámka\n')
root.update()
assert app.dirty['output']
assert app.after.drawing is None
expected = app.code.get('1.0','end-1c')
app.vars['feed'].set('1500')
assert app.code.get('1.0','end-1c') == expected
assert str(app.save_button['state']) == 'normal'
with tempfile.TemporaryDirectory() as temp:
    target = Path(temp)/'edited.nc'
    with patch('PrevodnikNC.filedialog.asksaveasfilename',return_value=str(target)):
        app.save(False)
    assert target.read_text(encoding='utf-8') == expected
    assert not app.dirty['output']
    app.replace_editor('input',edited)
    app.input_code.insert('end-1c','; vstup\n'); root.update()
    assert app.dirty['input']
    with patch('PrevodnikNC.messagebox.askyesno',return_value=False):
        assert not app.allow_replace(('input',))
    with patch('PrevodnikNC.filedialog.asksaveasfilename',return_value=str(Path(temp)/'input.nc')):
        app.save(False,source=True)
    assert (Path(temp)/'input.nc').read_text(encoding='utf-8') == app.input_code.get('1.0','end-1c')
    assert not app.dirty['input']
    assert app.filename.full_path == str(Path(temp)/'input.nc')
app.code.edit_undo(); root.update()
assert app.dirty['output']
numbered = '\n'.join(f'; řádek {i}' for i in range(1,151))
app.replace_editor('input',numbered)
app.input_editor.goto_line(78,error=True)
assert app.input_code.index('insert') == '78.0'
assert str(app.input_code.tag_ranges('error_line')[0]) == '78.0'
assert app.input_code.get('1.0','end-1c') == numbered
assert not app.dirty['input']
app.input_editor.goto_line(999)
assert app.input_code.index('insert') == '150.0'
app.error_editor = app.input_editor
app.jobs.put((None,None,ValueError('Řádek 78: Nepodporovaná adresa.'),app.revision))
with patch('PrevodnikNC.messagebox.showerror'):
    app.poll()
assert app.views.select() == str(app.editors_tab)
assert app.input_code.index('insert') == '78.0'
app.input_code.insert('78.0','; oprava '); root.update()
assert not app.input_code.tag_ranges('error_line')
with tempfile.TemporaryDirectory() as temp:
    outline = Path(temp)/'outline.nc'; holes = Path(temp)/'holes.nc'
    outline.write_text('G0 X0 Y0\nM3 S100\nG1 X20 Y10\nM5\nM2',encoding='utf-8')
    holes.write_text('G0 Z5\nG0 X10 Y5\nG1 Z-1\nG0 Z5\nM2',encoding='utf-8')
    with patch.object(app,'run_job',side_effect=lambda job,done,error_editor=None:done(job())), \
         patch('PrevodnikNC.messagebox.askyesno',return_value=True):
        with patch('PrevodnikNC.filedialog.askopenfilename',return_value=str(outline)):
            app.open_file()
        app.input_code.insert('end-1c','\n; edited outline'); root.update()
        with patch('PrevodnikNC.filedialog.askopenfilename',return_value=str(holes)):
            app.open_file(add=True)
        assert len(app.documents) == 2
        assert app.before.drawing.drill_points == [(10,5)]
        app.select_document(index=0)
        assert app.input_code.get('1.0','end-1c').endswith('; edited outline')
        assert app.dirty['input']
        app.select_document(index=1)
        app.vars['power'].set('400'); app.vars['mx'].set(True)
        app.convert()
        joined = app.code.get('1.0','end-1c')
        assert joined.splitlines().count('M2') == 1
        assert sum(s.burn for s in parse_nc(joined).strokes) == 2
        app.remove_document()
        assert len(app.documents) == 1
        assert app.input_code.get('1.0','end-1c').endswith('; edited outline')
        assert app.dirty['input']
root.destroy()
print('GUI OK: previews, saves, dirty state, undo, line navigation, added files, drill preview and combined conversion.')
