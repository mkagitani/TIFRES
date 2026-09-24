import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tifres_dependencies import STEPS, contract
from tifres_launcher import defaults, write_table
from tifres_provenance import snapshot, save_records
from tifres_status import Inspector


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tifres-status-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts, self.raw, self.output = [self.root / n for n in ('scripts', 'raw', 'fits')]
        for path in (self.scripts, self.raw, self.output): path.mkdir()
        legacy = Path(__file__).resolve().parents[1] / 'legacy'
        for step in STEPS: shutil.copy2(legacy / (step + '.py'), self.scripts)
        (self.scripts / 'cfg.py').write_text("raise RuntimeError('Inspection must not import cfg or legacy modules')")
        (self.scripts / 'psg').mkdir()
        (self.scripts / 'psg/psgrad586-596.txt').write_text('\n' * 14 + '588 1\n589 2\n')
        self.opts = {step: defaults(self.scripts, step) for step in STEPS}
        self.opts[STEPS[1]]['finterval'] = 8
        self.rows = []
        for n, name in enumerate(('dark', 'flat', 'sky', 'science', 'science2'), 1):
            row = dict(DSNO=str(n), FILENAME=name+'.fits', ORIGIN=name+'*.fits', DATATYPE='SKY',
                       DARKFRAME='' if n == 1 else 'dark.fits', WLFLAT='flat.fits', SKYFLAT='sky.fits' if n >= 4 else '',
                       WAVMAP='sky.wmp.fits', WAVSHIFT='0', FIBX0='1', FIBX1='2', FIBXWID='3', NFIBXY='2,2', IFIBIACT='',
                       PIXWAV1='1', CALWAV1='588.9', WAVSTEP1='0.1', CALWAVS='588.9,589.5', PIXWAVS='', PIXDWAVS='')
            self.rows.append(row)
            self.make_fits(self.raw / (name+'001.fits'), 'raw')
        self.row = self.rows[3]
        for row in self.rows:
            for step in STEPS if row['DSNO'] != '1' else STEPS[:1]:
                plan = contract(step, row, self.opts[step])
                for rel, kind in plan.products.items(): self.make_fits(self.output / rel, kind)
        self.counter = 0
        for row in self.rows:
            for step in STEPS if row['DSNO'] != '1' else STEPS[:1]: self.record(row, step)
        self.csv = self.root / 'datasets.csv'
        write_table(self.csv, list(self.row), self.rows)

    @staticmethod
    def make_fits(path, kind):
        path.parent.mkdir(parents=True, exist_ok=True)
        header = fits.Header()
        if kind in ('frame', 'raw'):
            data = np.ones((8, 12), dtype=np.float32)
        else:
            header['NFIBX'] = 2; header['NFIBY'] = 2
            data = np.ones((12,4,3) if kind == 'trace' else (2,2) if kind == 'image' else (4,12), dtype=np.float32)
        if kind in ('calibrated', 'image'):
            for k,v in dict(WAVMIN=588., WAVMAX=590., WAVSTEP=.1, CRVAL1=588., CDELT1=.1, CRPIX1=1., CTYPE1='WAVE').items(): header[k] = v
        hdus = [fits.PrimaryHDU(data, header)]
        if kind not in ('frame', 'raw'):
            hdus.extend([fits.ImageHDU(np.arange(4), name='FIBERS'), fits.ImageHDU(np.arange(4), name='IFIBERS')])
        if kind == 'trace': hdus.append(fits.ImageHDU(np.arange(12), name='YFIB'))
        if kind == 'spectrum':
            hdus.extend([fits.ImageHDU(data, name='spDat'), fits.ImageHDU(data, name='spDk')])
        fits.HDUList(hdus).writeto(path, overwrite=True)

    def record(self, row, step, state='Completed'):
        self.counter += 1
        stage = self.output / '.tifres-runs' / str(self.counter)
        stage.mkdir(parents=True)
        plan = contract(step, row, self.opts[step])
        for rel in plan.products:
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.output / rel, stage / rel)
        save_records(stage, [snapshot(step, row, self.opts[step], self.raw, self.output, self.scripts)], [plan])
        (stage / 'recovery.json').write_text(json.dumps({'state': state}))
        return stage

    def inspect(self, row=None):
        return Inspector(self.rows, self.scripts, self.raw, self.output, self.opts).inspect(row or self.row)

    def statuses(self): return [n['status'] for n in self.inspect()['steps']]

    def test_concise_historical_diagnostics_and_real_errors(self):
        before=self.statuses()
        runs=self.output/'.tifres-runs'
        (runs/'old-no-manifest').mkdir()
        (runs/'malformed').mkdir();(runs/'malformed/recovery.json').write_text('{broken')
        (runs/'failed').mkdir();(runs/'failed/recovery.json').write_text(json.dumps({'state':'Failed','error':'publication interrupted','replacing':'science.w5wc.fits'}))
        (runs/'missing-with-backup/.previous').mkdir(parents=True)
        report=self.inspect()
        self.assertEqual([n['status'] for n in report['steps']],before)
        self.assertEqual(report['warningCount'],3)
        self.assertEqual(report['historicalRuns'],self.counter+4)
        self.assertEqual(len(report['notes']),len(set(report['notes'])))
        self.assertTrue(any(d['severity']=='info' and 'old-no-manifest' in d['path'] for d in report['diagnostics']))
        self.assertTrue(any('publication interrupted' in d['message'] and d['severity']=='warning' for d in report['diagnostics']))
        self.assertTrue(any('manual recovery' in d['message'] for d in report['diagnostics']))

    def test_optional_manifest_does_not_hide_malformed_provenance(self):
        directory=self.output/'.tifres-runs'/'legacy-malformed'
        directory.mkdir()
        (directory/'provenance.json').write_text('{"version":1,"records":"broken"}')
        report=self.inspect()
        self.assertEqual(report['warningCount'],1)
        self.assertTrue(any('Malformed provenance' in d['message'] for d in report['diagnostics']))

    def test_all_products_present_and_proven_current(self):
        self.assertEqual(self.statuses(), ['Complete'] * 5)

    def test_missing_intermediate(self):
        (self.output / 'science.w5fsp.fits').unlink()
        report = self.inspect()
        self.assertEqual(report['steps'][2]['status'], 'Missing')
        self.assertNotEqual(report['steps'][4]['status'], 'Complete')
        self.assertTrue(any(d['status'] == 'Missing' for d in report['steps'][4]['dependencies']))

    def test_missing_calibration_identifies_actual_producer(self):
        (self.output / 'flat.fib.fits').unlink()
        node = self.inspect()['steps'][2]
        link = next(d for d in node['dependencies'] if d['role'].startswith('WLFLAT'))
        self.assertEqual(link['producers'], ['2'])
        self.assertEqual(link['status'], 'Missing')

    def test_outdated_upstream_propagates_without_timestamp_changes(self):
        path = self.raw / 'flat001.fits'; timestamp = path.stat().st_mtime_ns
        with fits.open(path, mode='update') as hdus: hdus[0].data[0,0] = 9
        os.utime(path, ns=(timestamp,timestamp))
        report = self.inspect()
        self.assertEqual(report['steps'][2]['status'], 'Outdated')
        self.assertEqual(report['steps'][4]['status'], 'Outdated')
        self.assertEqual(report['steps'][0]['status'], 'Complete')

    def test_changed_finterval_only_invalidates_trace_and_consumers(self):
        self.opts[STEPS[1]]['finterval'] = 16
        self.assertEqual(self.statuses(), ['Complete','Outdated','Outdated','Outdated','Outdated'])

    def test_changed_fibintwid_names_and_dependencies(self):
        self.opts[STEPS[4]]['fibintwid'] = 7
        node = self.inspect()['steps'][4]
        self.assertEqual(node['status'], 'Missing')
        self.assertIn('science.w7wc.fits', [o['path'] for o in node['outputs']])
        self.assertTrue(any('sky.w7wmp.fits' in d['path'] for d in node['dependencies']))
        self.assertEqual(self.statuses()[:4], ['Complete']*4)

    def test_changed_wlflat_and_wavmap(self):
        self.row['WLFLAT'] = 'sky.fits'
        self.assertEqual(self.statuses(), ['Complete','Complete','Outdated','Outdated','Outdated'])
        self.row['WLFLAT'] = 'flat.fits'
        self.row['WAVMAP'] = 'flat.wmp.fits'
        self.assertEqual(self.statuses(), ['Complete','Complete','Complete','Complete','Outdated'])

    def test_shared_calibrations_and_non_linear_graph(self):
        for row in self.rows[3:]:
            report = self.inspect(row)
            trace = next(d for d in report['steps'][2]['dependencies'] if d['role'].startswith('WLFLAT'))
            wavmap = next(d for d in report['steps'][4]['dependencies'] if d['role'] == 'WAVMAP')
            self.assertEqual(trace['producers'], ['2'])
            self.assertEqual(wavmap['producers'], ['3'])
            self.assertEqual(len([n for n in report['nodes'] if n['id'] == trace['node']]), 1)
            self.assertNotIn(report['steps'][1]['id'], [d['node'] for d in report['steps'][2]['dependencies']])
            self.assertNotIn(report['steps'][3]['id'], [d['node'] for d in report['steps'][4]['dependencies']])

    def test_literal_width_wavmap_resolves_actual_dsno_and_width(self):
        self.row['WAVMAP'] = 'sky.w5wmp.fits'
        self.opts[STEPS[4]]['fibintwid'] = 7
        link = next(d for d in self.inspect()['steps'][4]['dependencies'] if d['role'] == 'WAVMAP')
        self.assertEqual(link['producers'], ['3'])
        self.assertEqual(link['node'], '3:mkWavMap4d:5')
        self.assertTrue(link['path'].endswith('sky.w5wmp.fits'))

    def test_invalid_and_truncated_fits(self):
        path = self.output / 'science.fib.fits'
        path.write_bytes(path.read_bytes()[:3000])
        self.assertEqual(self.statuses()[1], 'Invalid')
        self.make_fits(path, 'frame')
        self.assertEqual(self.statuses()[1], 'Invalid')

    def test_required_hdu_and_wavelength_metadata(self):
        path = self.output / 'science.w5wc.fits'
        with fits.open(path, mode='update') as hdus: del hdus[0].header['WAVSTEP']
        self.assertEqual(self.statuses()[4], 'Invalid')
        path = self.output / 'science.w5fsp.fits'
        with fits.open(path, mode='update') as hdus: del hdus['IFIBERS']
        self.assertEqual(self.statuses()[2], 'Invalid')

    def test_historical_without_provenance_is_unknown_not_invalid(self):
        shutil.rmtree(self.output / '.tifres-runs')
        self.assertEqual(self.statuses(), ['Unknown']*5)

    def test_cancelled_and_incomplete_staged_products_are_ignored(self):
        (self.output / 'science.fib.fits').unlink()
        stage = self.output / '.tifres-runs/cancelled'
        stage.mkdir()
        self.make_fits(stage / 'science.fib.fits', 'trace')
        (stage / 'recovery.json').write_text('{"state":"Generating"}')
        self.assertEqual(self.statuses()[1], 'Missing')
        self.assertTrue(self.inspect()['notes'])

    def test_timestamps_alone_do_not_invalidate_identical_content(self):
        path = self.raw / 'flat001.fits'
        os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10**12))
        self.assertEqual(self.statuses(), ['Complete']*5)
        self.assertTrue(any('Timestamp hint' in r for n in self.inspect()['nodes'] for r in n['reasons']))

    def test_plot_and_overwrite_options_do_not_invalidate(self):
        self.opts[STEPS[4]]['flgPlot'] = not self.opts[STEPS[4]]['flgPlot']
        self.opts[STEPS[0]]['nxFig'] = 7
        self.assertEqual(self.statuses(), ['Complete']*5)

    def test_wavelength_parameters_scoped_to_actual_map_producer(self):
        self.row['CALWAV1'] = '589.0'
        self.assertEqual(self.statuses(), ['Complete','Complete','Complete','Outdated','Complete'])
        self.rows[2]['CALWAV1'] = '589.0'
        self.assertEqual(self.statuses()[4], 'Outdated')

    def test_external_and_ambiguous_calibration_is_unknown(self):
        self.rows.append(dict(self.rows[1], DSNO='6'))
        self.assertEqual(self.statuses()[2], 'Unknown')
        self.rows = [r for r in self.rows if r['DSNO'] not in ('2','6')]
        self.assertEqual(self.statuses()[2], 'Unknown')

    def test_changed_raw_identity_and_source(self):
        self.make_fits(self.raw / 'science002.fits', 'raw')
        self.assertEqual(self.statuses()[0], 'Outdated')
        path = self.scripts / 'mkFibFit4c.py'
        path.write_text(path.read_text(encoding='utf-8') + chr(10) + '# changed implementation' + chr(10), encoding='utf-8')
        self.assertEqual(self.statuses()[1], 'Outdated')

    def test_changed_skyflat_selection(self):
        self.row['SKYFLAT'] = ''
        # The product set changes too; existing science products require re-evaluation.
        self.assertEqual(self.statuses()[4], 'Outdated')
        self.assertEqual(self.statuses()[:4], ['Complete'] * 4)

    def test_cycles_are_reported_without_recursion_failure(self):
        self.rows[0]['DARKFRAME'] = 'dark.fits'
        report = self.inspect()
        self.assertNotEqual(report['steps'][0]['status'], 'Complete')
        self.assertTrue(any('Cyclic' in d['reason'] for n in report['nodes'] for d in n['dependencies']))

    def test_failed_run_record_cannot_establish_freshness(self):
        shutil.rmtree(self.output / '.tifres-runs')
        self.record(self.row, STEPS[1], 'Failed')
        self.assertEqual(self.statuses()[1], 'Unknown')

    def test_valid_external_replacement_without_matching_record_is_unknown(self):
        path = self.output / 'science.fib.fits'
        with fits.open(path, mode='update') as hdus: hdus[0].data[0,0,0] = 15
        self.assertEqual(self.statuses()[1], 'Unknown')

    def test_unknown_options_report_unknown_without_processing(self):
        self.opts[STEPS[1]]['madeUpOption'] = True
        self.assertEqual(self.statuses()[1], 'Unknown')
        self.assertEqual(self.statuses()[0], 'Complete')

    def test_unreferenced_flat_map_is_not_a_missing_pipeline_product(self):
        (self.output / 'flat.w5wmp.fits').unlink()
        report = self.inspect(self.rows[1])
        self.assertEqual(report['steps'][3]['status'], 'NotRequired')
        self.assertEqual(report['steps'][3]['dependencies'], [])
        self.assertEqual(report['steps'][4]['status'], 'Complete')
        science = self.inspect()
        self.assertEqual([n['status'] for n in science['steps']], ['Complete'] * 5)
        self.assertFalse(any(n['id'] == '2:mkWavMap4d:5' for n in science['nodes']))

    def test_referenced_flat_map_is_still_required(self):
        (self.output / 'flat.w5wmp.fits').unlink()
        for reference in ('flat.wmp.fits', 'flat.w5wmp.fits'):
            with self.subTest(reference=reference):
                self.row['WAVMAP'] = reference
                self.assertEqual(self.inspect(self.rows[1])['steps'][3]['status'], 'Missing')
                dependency = next(d for d in self.inspect()['steps'][4]['dependencies'] if d['role'] == 'WAVMAP')
                self.assertEqual(dependency['producers'], ['2'])
                self.assertEqual(dependency['status'], 'Missing')

    def test_actual_referenced_sky_map_missing_remains_visible(self):
        (self.output / 'flat.w5wmp.fits').unlink()
        (self.output / 'sky.w5wmp.fits').unlink()
        report = self.inspect(self.rows[1])
        self.assertEqual(report['steps'][3]['status'], 'NotRequired')
        dependency = next(d for d in report['steps'][4]['dependencies'] if d['role'] == 'WAVMAP')
        self.assertEqual(dependency['status'], 'Missing')
        self.assertEqual(dependency['producers'], ['3'])

    def test_unrequired_map_honors_literal_width_and_parameter_errors(self):
        (self.output / 'flat.w5wmp.fits').unlink()
        self.row['WAVMAP'] = 'flat.w5wmp.fits'
        self.opts[STEPS[4]]['fibintwid'] = 7
        self.assertEqual(self.inspect(self.rows[1])['steps'][3]['status'], 'Missing')
        self.opts[STEPS[4]]['fibintwid'] = 'invalid'
        self.assertNotEqual(self.inspect(self.rows[1])['steps'][3]['status'], 'NotRequired')

    def test_read_only_cli_and_no_legacy_import(self):
        def hashes(): return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        before = hashes()
        proc = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve().parents[1] / 'tifres_status.py'),
            '--script-dir', str(self.scripts), '--csv', str(self.csv), '--raw-dir', str(self.raw), '--fits-dir', str(self.output),
            '--dsno', '4', '--options-json', json.dumps(self.opts)], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(json.loads(proc.stdout)['steps']), 5)
        self.assertEqual(before, hashes())


if __name__ == '__main__': unittest.main()
