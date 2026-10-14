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
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fiamko.PrevodnikNC')
    root = tk.Tk()
    if '--self-test' in sys.argv:
        root.withdraw()
    app = App(root)
    if '--self-test' in sys.argv:
        # Exercise bundled Tk, application imports and all main widgets.
        root.update_idletasks()
        assert app.test_editor.text.winfo_exists()
        assert app.mill_editor.text.winfo_exists()
        from milling_core import milling_test, preview_mill
        cnc,_=milling_test(0,0,10,10,2,2,1,.5,.02,.04,100,200,2,60,10000,2)
        assert any(stroke.burn for stroke in preview_mill(cnc).strokes)
        assert cnc.count('M3 S10000')==1
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
        assert 'tnegative' in app.vars and 'ccompare' not in app.vars
        app.show_help()
        book=next(w for w in app.help_window.winfo_children() if isinstance(w,tk.ttk.Notebook))
        assert len(book.tabs())==3
        for tab in book.tabs():
            frame=book.nametowidget(tab)
            page=next(w for w in frame.winfo_children() if isinstance(w,tk.Text))
            assert len(page.get('1.0','end-1c'))>1000
            assert 'Cannot read manual' not in page.get('1.0','end-1c')
        app.help_window.destroy()
        app.save_preferences()
        assert app.preferences_path.exists()
        root.destroy()
        check_folder.cleanup()
        return
    root.mainloop()


if __name__ == '__main__':
    main()
