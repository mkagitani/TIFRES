import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tifres_launcher as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tifres mock ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / 'scripts with spaces'
        self.raw = self.root / 'raw'; self.output = self.root / 'fits'
        for p in (self.scripts, self.raw, self.output): p.mkdir()
        self.csv = self.root / 'datasets.csv'
        (self.scripts / 'cfg.py').write_text("fileCsv='untouched'\noriginal_path='untouched'\nfits_path='untouched'\ncurrent_dir='untouched'\n", encoding='utf-8')
        self.cfg_hash = hashlib.sha256((self.scripts / 'cfg.py').read_bytes()).digest()
        self.columns = ['DSNO', 'DATATYPE', 'FILENAME', 'ORIGIN', 'DARKFRAME', 'WLFLAT', 'SKYFLAT', 'WAVMAP',
                        'WAVSHIFT', 'FIBX0', 'FIBX1', 'FIBXWID', 'NFIBXY', 'IFIBIACT', 'CALWAV1', 'WAVSTEP1',
                        'PIXWAV1', 'PIXWAVS', 'PIXDWAVS', 'CALWAVS', 'UNKNOWN'] + list(launcher.METADATA)
        row = dict.fromkeys(self.columns, '')
        row.update(DSNO='0900719925474099312345', DATATYPE='SKY  ', FILENAME='night/a.sp.fits', ORIGIN='raw{1,2}.fits',
                   WLFLAT='night/flat.sp.fits', WAVMAP='night/cal.wmp.fits', FIBX0='2', FIBX1='5', FIBXWID='6',
                   CALWAV1='588.9', WAVSTEP1='0.00293', PIXWAV1='1024', CALWAVS='588.9,589.5', UNKNOWN='Keep, "quotes"\nand lines')
        self.rows = [row, dict.fromkeys(self.columns, '')]
        launcher.write_table(self.csv, self.columns, self.rows)
        (self.raw / 'raw1.fits').write_bytes(b'mock raw input, not observation data')
        self.mock_sp()

    def mock_sp(self, body=None):
        if body is None:
            body = '''
    import cfg, pandas as pd, json
    from pathlib import Path
    from astropy.io import fits
    import numpy as np
    frame = pd.read_csv(cfg.fileCsv)
    assert isinstance(dsno, list) and all(isinstance(i, int) for i in dsno)
    assert frame.iloc[0].DSNO == dsno[0]
    assert f"{frame.iloc[0].DSNO:.0f}" == str(dsno[0])
    assert flgPause is False
    assert Path(cfg.original_path, 'raw1.fits').is_file()
    target = Path(cfg.fits_path, frame.iloc[0].FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(np.zeros((2,2))).writeto(target, overwrite=True)
    fits.PrimaryHDU(np.zeros((2,2))).writeto(target.with_suffix('.m.fits'), overwrite=True)
    frame.at[0, 'EXPTIME'] = 12.5
    frame.to_csv(cfg.fileCsv, index=False)
    print('MOCK OPTIONS ' + json.dumps(dict(nxFig=nxFig, nyFig=nyFig, overwrite=overwrite)))
'''
        (self.scripts / 'mkSpFrames4f.py').write_text('def mkSpFrames4f(dsno,overwrite=True,flgPause=True,nxFig=2,nyFig=5):\n' + body + "\nif __name__ == '__main__': raise RuntimeError('Must import callable, not run main')\n", encoding='utf-8')

    def call(self, *extra):
        return subprocess.run([sys.executable, '-B', str(Path(launcher.__file__)), '--script-dir', str(self.scripts),
                               '--csv', str(self.csv), '--raw-dir', str(self.raw), '--fits-dir', str(self.output),
                               '--step', 'mkSpFrames4f', '--dsno', self.rows[0]['DSNO'], *extra],
                              capture_output=True, text=True, encoding='utf-8', timeout=60)

    def test_successful_mock_run_records_provenance_without_fits_changes(self):
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = list((self.output / '.tifres-runs').glob('*/provenance.json'))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text())['records'][0]
        self.assertEqual(record['dsno'], str(int(self.rows[0]['DSNO'])))
        self.assertEqual(record['step'], 'mkSpFrames4f')
        self.assertEqual(len(record['outputs']), 2)
        self.assertEqual(len(record['inputs']), 1)
        self.assertEqual(json.loads((records[0].parent / 'recovery.json').read_text())['state'], 'Completed')
        for name, value in record['outputs'].items():
            self.assertEqual(hashlib.sha256((self.output / name).read_bytes()).hexdigest(), value['sha256'])

    def test_png_routing_and_existing_overwrite_behavior(self):
        script = self.scripts / 'mkSpFrames4f.py'
        body = script.read_text()
        body = body.replace("    frame.to_csv(cfg.fileCsv, index=False)", """    frame.to_csv(cfg.fileCsv, index=False)
    png = Path(cfg.png_path) / 'mkSpFrames4f' / str(dsno[0]) / 'diagnostic.png'
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b'new PNG')""")
        script.write_text(body)
        custom = self.root / 'custom PNG'
        target = custom / 'mkSpFrames4f' / str(int(self.rows[0]['DSNO'])) / 'diagnostic.png'
        target.parent.mkdir(parents=True); target.write_bytes(b'old PNG')
        result = self.call('--png-dir', str(custom))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(target.read_bytes(), b'new PNG')
        self.assertFalse((self.scripts / 'png').exists())

    def test_dsno_arguments_exact(self):
        self.assertEqual(launcher.dsnos(['0001,2', '900719925474099312345']), [1,2,900719925474099312345])
        for values in ([], ['1.0'], ['1e3'], ['-2'], ['1', '01']):
            with self.assertRaises(ValueError): launcher.dsnos(values)

    def test_options_defaults_and_policy(self):
        original = launcher.defaults(self.scripts, 'mkSpFrames4f')
        self.assertEqual(original, dict(overwrite=True, flgPause=True, nxFig=2, nyFig=5))
        self.assertEqual(launcher.options(self.scripts, 'mkSpFrames4f', '{"nxFig":3}', False),
                         dict(overwrite=False, flgPause=False, nxFig=3, nyFig=5))
        for text in ('[]', '{"unknown":true}', '{"nxFig":0}', '{"nxFig":true}', '{"flgPause":"false"}'):
            with self.assertRaises(ValueError): launcher.options(self.scripts, 'mkSpFrames4f', text, False)

    def test_configuration_overrides_without_cfg_write(self):
        cfg = launcher.configure(self.scripts, self.csv, self.raw, self.output)
        self.assertEqual(cfg.fileCsv, str(self.csv))
        self.assertEqual(Path(cfg.fits_path), self.output)
        self.assertEqual(Path(cfg.original_path), self.raw)
        self.assertEqual(Path(cfg.current_dir), self.output)
        self.assertFalse(cfg.flgWpos)
        self.assertEqual(hashlib.sha256((self.scripts / 'cfg.py').read_bytes()).digest(), self.cfg_hash)

    def test_mock_processing_preserves_csv_and_cfg(self):
        original = self.csv.read_bytes()
        result = self.call('--options-json', '{"nxFig":3,"nyFig":4}')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"nxFig": 3', result.stdout)
        columns, after = launcher.read_table(self.csv)
        self.assertEqual(columns, self.columns)
        expected = [dict(r) for r in self.rows]; expected[0]['EXPTIME'] = '12.5'
        self.assertEqual(after, expected)
        self.assertTrue((self.output / 'night/a.sp.fits').is_file())
        self.assertTrue((self.output / 'night/a.sp.m.fits').is_file())
        self.assertEqual(next(self.root.glob('datasets.csv.*.bak')).read_bytes(), original)
        self.assertEqual(hashlib.sha256((self.scripts / 'cfg.py').read_bytes()).digest(), self.cfg_hash)

    def test_missing_raw_inputs_fail_before_import(self):
        (self.raw / 'raw1.fits').unlink()
        self.mock_sp("    raise RuntimeError('MOCK SHOULD NOT RUN')\n")
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No raw CCD files', result.stderr)
        self.assertNotIn('MOCK SHOULD NOT RUN', result.stderr)

    def test_missing_input_fits_and_auxiliary(self):
        with self.assertRaisesRegex(FileNotFoundError, 'Missing input FITS'):
            launcher.file_plan('mkWavMap4d', self.rows[:1], {'fibintwid':5}, self.raw, self.output, self.scripts)
        for name in ('a.sp.w5fsp.fits', 'flat.sp.w5fsp.fits'):
            p = self.output / 'night' / name; p.parent.mkdir(exist_ok=True); p.touch()
        with self.assertRaisesRegex(FileNotFoundError, 'Missing solar reference'):
            launcher.file_plan('mkWavMap4d', self.rows[:1], {'fibintwid':5}, self.raw, self.output, self.scripts)

    def test_existing_secondary_product_protected(self):
        p = self.output / 'night/a.sp.m.fits'; p.parent.mkdir(); p.write_bytes(b'original')
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('enable overwrite explicitly', result.stderr)
        self.assertEqual(p.read_bytes(), b'original')
        result = self.call('--overwrite')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(p.read_bytes(), b'original')

    def test_error_exit_and_missing_outputs(self):
        original = self.csv.read_bytes()
        self.mock_sp("    raise RuntimeError('mock failure')\n")
        result = self.call()
        self.assertNotEqual(result.returncode, 0); self.assertIn('mock failure', result.stderr)
        self.mock_sp("    print('silently returned')\n")
        result = self.call()
        self.assertNotEqual(result.returncode, 0); self.assertIn('did not produce', result.stderr)
        self.assertEqual(self.csv.read_bytes(), original)

    def test_unexpected_input_fails_instead_of_hanging(self):
        self.mock_sp("    input('unexpected prompt')\n")
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Legacy requested console input', result.stderr)

    def test_noninteractive_backend_and_restore(self):
        import matplotlib
        with launcher.adapters(self.csv, self.columns, self.rows, {int(self.rows[0]['DSNO'])}):
            matplotlib.use('Qt5Agg')
            self.assertEqual(matplotlib.get_backend().lower(), 'agg')
            import matplotlib.pyplot as plt
            plt.show(); plt.pause(0)

    def test_lock_and_path_safety(self):
        with launcher.exclusive_lock(self.output / 'lock'):
            with self.assertRaises(RuntimeError):
                with launcher.exclusive_lock(self.output / 'lock'): pass
        for value in ('../bad.fits', '/absolute.fits', 'C:\\absolute.fits'):
            with self.assertRaises(ValueError): launcher.relative(value)
        self.assertEqual(launcher.relative('night\\a.fits'), Path('night/a.fits'))

    def test_dispatch_all_five_steps_with_mock_functions(self):
        from astropy.io import fits
        import numpy as np
        self.rows[0]['DARKFRAME'] = 'night/dark.fits'
        launcher.write_table(self.csv, self.columns, self.rows)
        names = ('a.sp.fits', 'dark.fits', 'flat.sp.fib.fits', 'a.sp.w5fsp.fits',
                 'flat.sp.w5fsp.fits', 'cal.w5wmp.fits')
        for name in names:
            target = self.output / 'night' / name
            target.parent.mkdir(exist_ok=True)
            fits.PrimaryHDU(np.zeros((2,2))).writeto(target, overwrite=True)
        psg = self.scripts / 'psg'; psg.mkdir()
        (psg / 'psgrad586-596.txt').write_text('mock reference')
        expected = {
            'mkSpFrames4f': ('night/a.sp.fits', 'night/a.sp.m.fits'),
            'mkFibFit4c': ('night/a.sp.fib.fits',),
            'mkFibSpec4d': ('night/a.sp.w5fsp.fits',),
            'mkWavMap4d': ('night/a.sp.w5wmp.fits',),
            'mkWcalSpec4d': ('night/a.sp.w5wc.fits', 'night/a.sp.w5img.fits')}
        for step in launcher.STEPS:
            with self.subTest(step=step):
                values = launcher.defaults(Path(launcher.__file__).parent / 'legacy', step)
                signature = ','.join(f'{k}={v!r}' for k,v in values.items())
                body = f"""def {step}(dsno,{signature}):
    import cfg, matplotlib
    matplotlib.use('Qt5Agg')
    from pathlib import Path
    import numpy as np
    from astropy.io import fits
    assert matplotlib.get_backend().lower() == 'agg'
    assert dsno == [{int(self.rows[0]['DSNO'])}]
    for name in {expected[step]!r}:
        target = Path(cfg.fits_path, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        fits.PrimaryHDU(np.zeros((2,2))).writeto(target, overwrite=True)
    print('CALLED {step}')
"""
                (self.scripts / (step + '.py')).write_text(body, encoding='utf-8')
                for name in expected[step]:
                    target = self.output / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b'protected prior FITS')
                blocked = self.call('--step', step)
                self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
                for name in expected[step]:
                    self.assertEqual((self.output / name).read_bytes(), b'protected prior FITS')
                result = self.call('--step', step, '--overwrite')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('CALLED ' + step, result.stdout)

    def test_multi_dsno_selection_and_missing_identifier(self):
        second = dict(self.rows[0]); second['DSNO'] = '000123'
        rows = self.rows + [second]
        selected = launcher.select_rows(rows, launcher.dsnos(['123', self.rows[0]['DSNO']]))
        self.assertEqual([r['DSNO'] for r in selected], ['000123', self.rows[0]['DSNO']])
        with self.assertRaisesRegex(ValueError, 'not present'):
            launcher.select_rows(rows, [999])

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate option'):
            launcher.options(self.scripts, 'mkSpFrames4f', '{"nxFig":1,"nxFig":2}', False)
    def test_all_original_signatures_are_preserved(self):
        legacy = Path(launcher.__file__).parent / 'legacy'
        expected = {
            'mkSpFrames4f': dict(overwrite=True,flgPause=True,nxFig=2,nyFig=5),
            'mkFibFit4c': dict(flgPause=False,finterval=1),
            'mkFibSpec4d': dict(flgPause=False,flgShowAll=False,fibintwid=5,overwrite=True),
            'mkWavMap4d': dict(flgPause=True,fibintwid=5,flgNoWLflat=False,fiberCoefDegree=2),
            'mkWcalSpec4d': dict(flgPlot=True,fibintwid=5,overwrite=True,flgNoWLflat=False)}
        for step in launcher.STEPS: self.assertEqual(launcher.defaults(legacy, step), expected[step])


if __name__ == '__main__': unittest.main()
