import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from astropy.io import fits
import test_status as fixtures
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tifres_quicklook import inspect_raw, plan, owned_products, viewer_product, STEPS
from tifres_launcher import METADATA, write_table

class QuickLookTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StatusTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.row = copy.deepcopy(f.row)
        for key in METADATA:
            self.row.setdefault(key, '')
        self.request = dict(row=self.row, raw=str(f.raw), fits=str(f.output), scripts=str(f.scripts),
                            options={s:json.dumps(f.opts[s]) for s in STEPS}, force=False)

    def test_exact_calibrations_and_default_reuse(self):
        result = plan(self.request)
        self.assertEqual([s['step'] for s in result['steps']], list(STEPS))
        self.assertTrue(all(s['reuse'] for s in result['steps']))
        self.assertIn('sky.w5wmp.fits', '\n'.join(result['calibrations']))
        self.assertNotIn('flat.w5wmp.fits', '\n'.join(result['calibrations']))
        self.assertTrue(result['viewer'].endswith('science.w5wc.fits'))
        self.assertNotIn(str(self.fixture.output/'sky.w5wc.fits'),result['steps'][-1]['outputs'])

    def test_force_reruns_only_science_steps(self):
        self.request['force'] = True
        self.assertTrue(all(not s['reuse'] for s in plan(self.request)['steps']))

    def test_missing_calibration_blocks_even_when_science_exists(self):
        for filename in ('dark.fits','flat.fib.fits','flat.w5fsp.fits','sky.w5wmp.fits','sky.w5fsp.fits'):
            with self.subTest(filename=filename):
                path=self.fixture.output/filename
                original=path.read_bytes();path.unlink()
                with self.assertRaisesRegex(ValueError,'Required calibration'):
                    plan(self.request)
                path.write_bytes(original)

    def test_partial_and_invalid_products_require_explicit_force(self):
        path=self.fixture.output/'science.m.fits';path.unlink()
        with self.assertRaisesRegex(ValueError,'Incomplete product set'):
            plan(self.request)
        path.write_bytes(b'incomplete')
        with self.assertRaisesRegex(ValueError,'Invalid existing product'):
            plan(self.request)
        self.request['force']=True
        self.assertFalse(plan(self.request)['steps'][0]['reuse'])

    def test_calibration_collision_is_rejected(self):
        self.row['DARKFRAME']='science.fits'
        with self.assertRaisesRegex(ValueError,'collision'):
            plan(self.request)

    def test_raw_pattern_exact_set_ambiguity_headers_and_conflict(self):
        raw=self.fixture.raw
        paths=[raw/f'veA01_{i:04d}.fits' for i in (1,2)]
        for path in paths:
            fixtures.StatusTests.make_fits(path,'raw')
            with fits.open(path,mode='update') as hdus:
                hdus[0].header['DATE-OBS']='2026-09-14T12:00:00'
                hdus[0].header['EXPTIME']=12.5
        result=inspect_raw(raw,paths)
        self.assertEqual(result['origin'],'veA01_*.fits')
        self.assertFalse(result['ambiguous'])
        self.assertEqual(result['observingDate'],'2026-09-14')
        self.assertEqual(result['metadata']['EXPTIME'],'12.5')
        self.assertNotIn('EXPSTART',result['metadata'])
        fixtures.StatusTests.make_fits(raw/'veA01_0003.fits','raw')
        result=inspect_raw(raw,paths)
        self.assertTrue(result['ambiguous'])
        self.assertTrue(any('EXPTIME differs' in n for n in result['notes']))
        self.assertNotIn('EXPTIME',result['metadata'])
        self.assertEqual(len(result['files']),3)

    def test_single_brace_and_raw_escape(self):
        raw=self.fixture.raw
        a,b=raw/'one.fits',raw/'different.fits'
        for p in (a,b):fixtures.StatusTests.make_fits(p,'raw')
        self.assertEqual(inspect_raw(raw,[a])['origin'],'one.fits')
        result=inspect_raw(raw,[a,b])
        self.assertFalse(result['ambiguous'])
        self.assertEqual(set(result['files']),{str(a),str(b)})
        with self.assertRaisesRegex(ValueError,'inside configured'):
            inspect_raw(raw,[self.fixture.output/'dark.fits'])

    def test_options_must_agree(self):
        self.request['options'][STEPS[1]]=json.dumps(dict(fibintwid=8))
        with self.assertRaisesRegex(ValueError,'must agree'):
            plan(self.request)

    def test_quick_launcher_preserves_existing_sky_calibration(self):
        f=self.fixture
        # Mock callable only: no actual numerical code is run.
        (f.scripts/'cfg.py').write_text("fileCsv='unused'\n")
        (f.scripts/'mkWcalSpec4d.py').write_text("""def mkWcalSpec4d(dsno,flgPlot=False,fibintwid=5,overwrite=True,flgNoWLflat=False):
    from pathlib import Path
    import cfg
    from astropy.io import fits
    import numpy as np
    for name in ('science.w5wc.fits','science.w5img.fits','sky.w5wc.fits'):
        fits.PrimaryHDU(np.full((2,2),42.)).writeto(Path(cfg.fits_path)/name,overwrite=True)
""")
        csv=f.root/'quick.csv';write_table(csv,list(self.row),[self.row])
        sky=f.output/'sky.w5wc.fits';before=sky.read_bytes()
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'tifres_launcher.py'),
            '--step',STEPS[-1],'--dsno',self.row['DSNO'],'--script-dir',str(f.scripts),'--csv',str(csv),
            '--raw-dir',str(f.raw),'--fits-dir',str(f.output),'--overwrite','--quick-look'],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(sky.read_bytes(),before)
        report=json.loads(result.stdout.splitlines()[0])
        self.assertEqual(set(report['outputs']),{'science.w5wc.fits','science.w5img.fits'})
        manifests=list((f.output/'.tifres-runs').glob('*/recovery.json'))
        latest=max(manifests,key=lambda p:p.stat().st_mtime_ns)
        self.assertNotIn('sky.w5wc.fits',json.loads(latest.read_text())['products'])

    def test_viewer_defaults_to_reported_wc(self):
        path=self.fixture.output/'science.w5wc.fits'
        self.assertEqual(viewer_product(path)['path'],str(path.resolve()))

    def test_matching_3d_companion_is_preferred_but_stale_cube_is_not(self):
        import numpy as np
        path=self.fixture.output/'exact.w5wc.fits'
        h=fits.Header(dict(NFIBX=10,NFIBY=12,CTYPE1='WAVE',CTYPE2='FIBERID',
            WAVMIN=588.,WAVMAX=588.7,WAVSTEP=.1,CRVAL1=588.,CDELT1=.1,CRPIX1=1.,CUNIT1='nm'))
        data=np.arange(960,dtype=np.float64).reshape(120,8)
        def write(target,array):
            fits.HDUList([fits.PrimaryHDU(array,h),fits.ImageHDU(np.arange(120),name='FIBERS'),
                fits.ImageHDU(np.arange(120),name='IFIBERS')]).writeto(target,overwrite=True)
        write(path,data)
        cube=path.with_name('exact.w5dcb.fits');write(cube,data.T.reshape(8,12,10))
        self.assertEqual(viewer_product(path)['path'],str(cube.resolve()))
        write(cube,data.T.reshape(8,12,10)+1)
        self.assertEqual(viewer_product(path)['path'],str(path.resolve()))
