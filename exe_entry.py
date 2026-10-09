"""Windows executable entry point, including a noninteractive packaging check."""
import sys
import os
from pathlib import Path
import tempfile
from recovery import atomic_write_text
from nc_core import test_pattern, parse_nc
import tkinter as tk
from PrevodnikNC import App


def main():
    check_folder = None
    if "--self-test" in sys.argv:
        check_folder = tempfile.TemporaryDirectory(prefix="PrevodnikNC-settings-check-")
        os.environ["APPDATA"] = check_folder.name
    root = tk.Tk()
    if '--self-test' in sys.argv:
        root.withdraw()
    app = App(root)
    if '--self-test' in sys.argv:
        # Exercise bundled Tk, application imports and all main widgets.
        root.update_idletasks()
        assert app.test_editor.text.winfo_exists()
        assert app.input_editor.text.winfo_exists()
        with tempfile.TemporaryDirectory(prefix='PrevodnikNC-check-') as folder:
            target = Path(folder) / 'overeni.nc'
            text, _ = test_pattern(0,0,10,10,1,1,0,.2,100,100,1000,1000)
            atomic_write_text(target,text)
            assert target.read_text(encoding='utf-8') == text
            assert any(stroke.burn for stroke in parse_nc(text).strokes)
        negative,_=test_pattern(0,0,12,16,1,1,0,.2,32.4,32.4,1800,1800,
                                trace_widths=[.3,.5,.8,1],negative=True)
        assert 'Sirky sloupecku zleva' in negative
        assert any(s.burn for s in parse_nc(negative).strokes)
        assert 'obrys celeho pole' not in negative
        app.vars['tnegative'].set(True)
        assert app.vars['tnegative'].get() is True
        app.save_preferences()
        assert app.preferences_path.exists()
        root.destroy()
        check_folder.cleanup()
        return
    root.mainloop()


if __name__ == '__main__':
    main()
