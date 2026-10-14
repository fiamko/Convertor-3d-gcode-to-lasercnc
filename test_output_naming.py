import unittest
from pathlib import Path
from PrevodnikNC import output_filename

class OutputNamingTests(unittest.TestCase):
    def test_cam_and_previous_export_suffixes(self):
        for name in ('verze7.drl_cnc.nc','verze7.drl_cnc_spojene_laser.nc',
                     'verze7-B_Cu.gbr_cnc.nc','verze7-F_Cu.gbrl.nc',
                     'verze7-PTH.drl.nc','verze7-grb_drl.nc','verze7-grb_cnc.nc',
                     'verze7.nc'):
            with self.subTest(name=name):
                self.assertEqual(output_filename(Path(name)), 'verze7-grb_drl.nc')
                self.assertEqual(output_filename(Path(name),True), 'verze7-grb_cnc.nc')
        self.assertEqual(output_filename('muj_projekt-v2.nc'), 'muj_projekt-v2-grb_drl.nc')
        self.assertEqual(output_filename(None), 'novy-grb_drl.nc')

    def test_save_dialog_uses_actual_output_technology(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from PrevodnikNC import App
        app=SimpleNamespace(path=Path('verze7.drl_cnc.nc'),
            documents=[{'path':Path('verze7.drl_cnc.nc')},{'path':Path('verze7-B_Cu.gbr.nc')}],
            output_path=None,last_directory='')
        for code,suffix in (('M3 S200\n','drl'),('(CNC PCB - povrch Z0)\n','cnc')):
            app.code=SimpleNamespace(get=lambda *args:code)
            with patch('PrevodnikNC.filedialog.asksaveasfilename',return_value='') as dialog:
                App.save(app,False)
            self.assertEqual(dialog.call_args.kwargs['initialfile'],f'verze7-grb_{suffix}.nc')
        app.output_path=Path('vlastni-jmeno.nc')
        with patch('PrevodnikNC.filedialog.asksaveasfilename',return_value='') as dialog:
            App.save(app,False)
        self.assertEqual(dialog.call_args.kwargs['initialfile'],'vlastni-jmeno.nc')
