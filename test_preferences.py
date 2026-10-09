import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class Preferences(unittest.TestCase):
    def test_restart_and_corrupt_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            env=dict(os.environ,APPDATA=folder)
            prefix="import tkinter as tk\nfrom PrevodnikNC import App\nroot=tk.Tk(); root.withdraw(); app=App(root)\n"
            def run(code):
                subprocess.run([sys.executable,'-c',prefix+code+'\nroot.destroy()'],env=env,check=True,timeout=30)
            run("""app.vars['power'].set('660')
app.vars['fmax'].set('3000')
app.vars['mx'].set(True)
app.vars['contour_count'].set('2')
app.vars['tborder'].set('2')
app.vars['tnegative'].set(True)
app.vars['trace_widths'].set('0,3; 0,5; 0,8; 1')
app.recipe_name.set('PCB test')
app.recipe_note.set('ověřeno')
app.before.travel.set(True)
app.notebook.select(1)
app.save_preferences()
assert app.preferences_path.exists()""")
            run("""assert app.vars['power'].get()=='660'
assert app.vars['fmax'].get()=='3000'
assert app.vars['mx'].get() is True
assert app.vars['contour_count'].get()=='2'
assert app.vars['tborder'].get()=='2'
assert app.vars['tnegative'].get() is True
assert app.vars['trace_widths'].get()=='0,3; 0,5; 0,8; 1'
assert app.recipe_name.get()=='PCB test'
assert app.recipe_note.get()=='ověřeno'
assert app.before.travel.get() is True
assert app.notebook.index('current')==1
assert not app.documents
assert not app.test_output""")
            path=Path(folder)/'PrevodnikNC'/'nastaveni.json'
            path.write_text('{bad',encoding='utf-8')
            run("assert app.vars['power'].get()==''\nassert 'nelze načíst' in app.status.get()")
            path.write_text('{"version":1,"values":{"laser":"BAD","mx":"false","power":"380"}}',encoding='utf-8')
            run("assert app.vars['laser'].get()=='M3'\nassert app.vars['mx'].get() is False\nassert app.vars['power'].get()=='380'")

if __name__=='__main__': unittest.main()
