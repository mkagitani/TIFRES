"""Read-only structural and provenance inspection. Never imports a legacy module."""
import argparse
import json
import re
from pathlib import Path
import sys
import warnings
import numpy as np
from astropy.io import fits
from tifres_dependencies import STEPS, LABELS, contract, parameters, raw_matches, relative, under
from tifres_provenance import identity, snapshot


def validate_fits(path, kind):
    """Basic consumer-compatible contracts, not a scientific quality assessment."""
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter('always')
        with fits.open(path, mode='readonly', memmap=False, checksum=True) as hdus:
            hdus.verify('exception')
            for hdu in hdus:
                data = hdu.data  # force complete data reads, including extensions
                if data is not None and data.size == 0: raise ValueError('Empty HDU data.')
            data, header = hdus[0].data, hdus[0].header
            rank = 3 if kind == 'trace' else 2
            if data is None or data.ndim != rank or min(data.shape) <= 0:
                raise ValueError(f'{kind} requires a nonempty {rank}D primary array.')
            if not np.isfinite(data).any(): raise ValueError('Primary array contains no finite samples.')
            if kind not in ('frame', 'raw'):
                nfibx, nfiby = header['NFIBX'], header['NFIBY']
                if not isinstance(nfibx, int) or not isinstance(nfiby, int) or min(nfibx, nfiby) <= 0:
                    raise ValueError('Invalid NFIBX/NFIBY.')
                fibers, active = hdus['FIBERS'].data, hdus['IFIBERS'].data
                n = nfibx * nfiby
                if fibers.ndim != 1 or len(fibers) != n or not np.array_equal(fibers, np.arange(n)):
                    raise ValueError('FIBERS does not match NFIBX × NFIBY.')
                if active.ndim != 1 or not len(active) or not np.issubdtype(active.dtype, np.integer) or len(set(active)) != len(active) or np.any(active < 0) or np.any(active >= n):
                    raise ValueError('Invalid active fiber indices.')
                if kind == 'trace':
                    if data.shape[1:] != (n, 3): raise ValueError('Trace must have shape (pixels, fibers, 3).')
                    if hdus['YFIB'].data.shape != (data.shape[0],): raise ValueError('YFIB length differs from trace pixels.')
                elif kind == 'image':
                    if data.shape != (nfiby, nfibx): raise ValueError('Image shape differs from fiber grid.')
                elif data.shape[0] != n: raise ValueError('Spectrum/map fiber dimension differs from fiber grid.')
                if kind == 'spectrum':
                    for name in ('spDat', 'spDk'):
                        if hdus[name].data.shape != data.shape: raise ValueError(f'{name} shape differs from primary.')
                if kind in ('calibrated', 'image'):
                    for key in ('WAVMIN', 'WAVMAX', 'WAVSTEP', 'CRVAL1', 'CDELT1', 'CRPIX1'):
                        if not np.isfinite(float(header[key])): raise ValueError(f'Invalid {key}.')
                    if header['WAVSTEP'] <= 0 or header['CDELT1'] <= 0 or header['CTYPE1'] != 'WAVE':
                        raise ValueError('Invalid wavelength-axis metadata.')
            if notices: raise ValueError('; '.join(str(n.message) for n in notices))
            return tuple(data.shape)


class Inspector:
    def __init__(self, rows, scripts, raw, output, step_options=None):
        from tifres_launcher import options
        self.rows = [r for r in rows if r.get('DSNO', '').strip()]
        self.scripts, self.raw, self.output = map(lambda p: Path(p).resolve(), (scripts, raw, output))
        self.opts, self.option_errors = {}, {}
        for step in STEPS:
            try:
                text = (step_options or {}).get(step, '{}')
                self.opts[step] = options(self.scripts, step, text if isinstance(text, str) else json.dumps(text), False)
            except Exception as ex: self.option_errors[step] = str(ex)
        self.nodes, self.visiting, self.cache, self.checks = {}, set(), {}, {}
        self.records, self.notes = [], []
        self.historical_runs, self.diagnostics = 0, []
        # Missing manifests predate the recoverable-publication protocol in some
        # historical directories. They never establish provenance, but absence
        # alone is not an error. Publication evidence still requires recovery.
        runs = self.output / '.tifres-runs'
        if runs.is_dir():
            for directory in sorted(runs.iterdir(), key=lambda p: p.stat().st_mtime_ns, reverse=True):
                if not directory.is_dir(): continue
                self.historical_runs += 1
                try:
                    manifest = directory / 'recovery.json'
                    if not manifest.exists():
                        provenance = directory / 'provenance.json'
                        if provenance.exists(): self.read_records(provenance)  # Validate, never treat as completed.
                        evidence = any((directory / n).exists() for n in ('.previous', '.prepared'))
                        self.diagnostic('warning' if evidence else 'info', directory,
                            'Missing recovery.json with retained publication backups; manual recovery inspection required.'
                            if evidence else 'Historical directory without optional recovery manifest; not a provenance source.')
                        continue
                    recovery = json.loads(manifest.read_text(encoding='utf-8'))
                    if not isinstance(recovery, dict) or not isinstance(recovery.get('state'), str):
                        raise ValueError('Recovery manifest must be an object with a state.')
                    state = recovery['state']
                    known = ('Completed', 'Generating', 'Cancelled', 'Failed', 'Preparing publication', 'Publishing')
                    if state not in known:
                        raise ValueError(f'Unrecognized recovery state: {state}')
                    if state != 'Completed':
                        serious = state in ('Failed', 'Preparing publication', 'Publishing') or bool(recovery.get('replacing') or recovery.get('published') or recovery.get('error'))
                        self.diagnostic('warning' if serious else 'info', directory,
                            f'Retained {state} run (not a product source). ' + str(recovery.get('error', '')) +
                            (f" Publication recovery: replacing={recovery.get('replacing')}, published={recovery.get('published')}" if recovery.get('replacing') or recovery.get('published') else ''))
                        continue
                    path = directory / 'provenance.json'
                    if not path.exists(): continue
                    self.records.extend(self.read_records(path))
                except (OSError, ValueError, KeyError, TypeError) as ex:
                    self.diagnostic('warning', directory, f'Unreadable recovery/provenance: {ex}')

    @staticmethod
    def read_records(path):
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict) or payload.get('version') != 1:
            raise ValueError('Unsupported provenance version/structure.')
        records = payload['records']
        if not isinstance(records, list) or any(
            not isinstance(r, dict) or not isinstance(r.get('dsno'), str) or not isinstance(r.get('step'), str)
            or any(not isinstance(r.get(k), dict) for k in ('parameters', 'inputs', 'outputs', 'source'))
            for r in records):
            raise ValueError('Malformed provenance records.')
        return records

    def diagnostic(self, severity, directory, message):
        item = dict(severity=severity, path=str(directory), message=message.strip())
        if item not in self.diagnostics:
            self.diagnostics.append(item)
            self.notes.append(f'{severity.upper()}: {directory}: {message.strip()}')

    def fingerprint(self, path):
        path = Path(path)
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        if key not in self.cache: self.cache[key] = identity(path)
        return self.cache[key]

    def check(self, path, kind):
        path = Path(path)
        if not path.exists(): return 'Missing', f'Missing {kind}: {path}'
        try:
            key = (str(path), kind, path.stat().st_mtime_ns, path.stat().st_size)
            if key not in self.checks:
                if kind == 'text':
                    # Legacy solar reference skips 14 header lines and uses two columns.
                    values = np.loadtxt(path, skiprows=14)
                    if values.ndim != 2 or values.shape[1] < 2 or not np.isfinite(values[:, :2]).all():
                        raise ValueError('Solar reference requires two finite columns.')
                else: validate_fits(path, kind)
                self.checks[key] = True
            return 'Valid', ''
        except PermissionError as ex: return 'Unknown', f'Cannot inspect {path}: {ex}'
        except Exception as ex: return 'Invalid', f'Invalid {kind} {path}: {ex}'

    @staticmethod
    def map_width(item, row):
        # A WAVMAP cell can contain either the legacy template .wmp.fits or an
        # already resolved .w5wmp.fits path. Match the actual producer expression
        # against CSV FILENAME, rather than assuming a DSNO from a suffix.
        name = str(relative(row['FILENAME']))
        pattern = re.escape(name).replace(re.escape('.fits'), r'\.w([1-9][0-9]*)wmp\.fits')
        match = re.fullmatch(pattern, str(item.path))
        if not match: return None
        width = int(match.group(1))
        return width if name.replace('.fits', f'.w{width}wmp.fits') == str(item.path) else None

    def producer(self, item):
        if item.producer is None: return []
        def matches(row):
            try:
                name = str(relative(row['FILENAME']))
                if item.role == 'WAVMAP': return self.map_width(item, row) is not None
                return name == item.base
            except (ValueError, KeyError): return False
        return [r for r in self.rows if matches(r)]

    def node(self, row, step, width=None):
        opts = dict(self.opts.get(step, {}))
        if width is not None and 'fibintwid' in opts: opts['fibintwid'] = width
        key = f'{int(row["DSNO"])}:{step}:{opts.get("fibintwid", "-")}'
        if key in self.visiting:
            return {'id': key, 'status': 'Unknown', 'dsno': row['DSNO'], 'step': step, 'reasons': ['Cyclic CSV calibration dependency.']}
        if key in self.nodes: return self.nodes[key]
        self.visiting.add(key)
        node = dict(id=key, dsno=str(int(row['DSNO'])), step=step, label=LABELS[STEPS.index(step)],
                    status='Unknown', outputs=[], dependencies=[], reasons=[])
        self.nodes[key] = node
        try:
            if step in self.option_errors: raise ValueError(self.option_errors[step])
            plan = contract(step, row, opts)
            for rel, kind in plan.products.items():
                path = under(self.output, rel)
                state, reason = self.check(path, kind)
                node['outputs'].append({'path': str(rel), 'status': state})
                if reason: node['reasons'].append(reason)
            deps = list(plan.inputs)
            for item in deps:
                path = under(self.scripts if item.root == 'scripts' else self.output, item.path)
                state, reason = self.check(path, item.kind)
                candidates = self.producer(item)
                link = dict(role=item.role, path=str(path), status=state, producers=[str(int(r['DSNO'])) for r in candidates], reason=reason, node=None)
                if len(candidates) == 1:
                    producer_width = self.map_width(item, candidates[0]) if item.role == 'WAVMAP' else opts.get('fibintwid')
                    upstream = self.node(candidates[0], item.producer, producer_width)
                    link['node'] = upstream['id']
                    if state == 'Valid': link['status'] = upstream['status']
                    link['reason'] = '; '.join(upstream['reasons']) if not reason else reason
                elif item.producer:
                    link['reason'] += ' No unique CSV producer; treat as external calibration.'
                    if state == 'Valid': link['status'] = 'Unknown'
                node['dependencies'].append(link)
            if step == STEPS[0]:
                matches = raw_matches(row, self.raw)
                if not matches:
                    node['dependencies'].append(dict(role='ORIGIN', path=str(self.raw / row.get('ORIGIN', '')), status='Missing', producers=[], node=None, reason='No raw inputs match ORIGIN.'))
                for path in matches:
                    state, reason = self.check(path, 'raw')
                    node['dependencies'].append(dict(role='raw CCD', path=str(path), status=state, producers=[], node=None, reason=reason))
            output_states = {o['status'] for o in node['outputs']}
            records = [r for r in self.records if r.get('dsno') == str(int(row['DSNO'])) and r.get('step') == step]
            # Prefer evidence tied to the exact current output bytes, then matching
            # width. A record from another width explains the missing new products.
            record = None
            for candidate in records:
                if str(next(iter(plan.products))) in candidate.get('outputs', {}):
                    if record is None: record = candidate
                    try:
                        if all(self.fingerprint(under(self.output, p)) == candidate['outputs'].get(str(p)) for p in plan.products):
                            record = candidate; break
                    except (OSError, RuntimeError): pass
            outdated, uncertain = False, False
            if record:
                if record.get('parameters') != parameters(step, row, opts):
                    outdated = True; node['reasons'].append('Relevant CSV parameters or processing options changed since generation.')
                try:
                    now = snapshot(step, row, opts, self.raw, self.output, self.scripts, self.fingerprint)
                    if now['inputs'] != record.get('inputs'):
                        outdated = True; node['reasons'].append('Required input identities/content changed since generation.')
                    if now['source'] != record.get('source'):
                        outdated = True; node['reasons'].append('Processing source changed since generation.')
                    if any(self.fingerprint(under(self.output, relative(p))) != v for p,v in record['outputs'].items()):
                        uncertain = True; node['reasons'].append('Products differ from recorded output identities; generation is unknown.')
                except (OSError, ValueError, RuntimeError) as ex:
                    uncertain = True; node['reasons'].append(f'Cannot verify provenance: {ex}')
            else:
                uncertain = True; node['reasons'].append('No matching completed provenance; historical products are not assumed current.')
                if records: node['reasons'].append('Recorded outputs use another filename/width; verify fibintwid and FILENAME.')
            for dep in node['dependencies']:
                if dep['status'] == 'Outdated':
                    outdated = True; node['reasons'].append(f'Outdated upstream {dep["role"]}: {dep["path"]}')
                elif dep['status'] not in ('Complete', 'Valid'):
                    uncertain = True; node['reasons'].append(f'{dep["status"]} dependency {dep["role"]}: {dep["path"]}')
            # Timestamps explain possible staleness, never establish validity.
            existing = [under(self.output, p) for p in plan.products if under(self.output, p).is_file()]
            if existing:
                oldest = min(p.stat().st_mtime_ns for p in existing)
                for dep in node['dependencies']:
                    path = Path(dep['path'])
                    if path.is_file() and path.stat().st_mtime_ns > oldest:
                        node['reasons'].append(f'Timestamp hint only: input is newer than output: {path}')
            node['status'] = ('Invalid' if 'Invalid' in output_states else 'Missing' if 'Missing' in output_states
                              else 'Outdated' if outdated else 'Unknown' if uncertain or 'Unknown' in output_states else 'Complete')
            if node['status'] == 'Complete': node['reasons'].append('Structure, recorded inputs/options and all known dependencies agree.')
        except Exception as ex:
            node['reasons'].append(f'Cannot establish contract/freshness: {ex}')
        finally: self.visiting.remove(key)
        return node

    def unrequired_missing_map(self, row):
        """An optional callable is not automatically a pipeline prerequisite."""
        if STEPS[3] in self.option_errors or STEPS[4] in self.option_errors:
            return None
        try:
            name = str(relative(row['FILENAME']))
            if not name.endswith('.fits'): return None
            width = self.opts[STEPS[3]]['fibintwid']
            path = relative(name.replace('.fits', f'.w{width}wmp.fits'))
            if under(self.output, path).exists(): return None
            calibration_width = self.opts[STEPS[4]]['fibintwid']
            for consumer in self.rows:
                reference = consumer.get('WAVMAP', '')
                if not reference.strip(): continue
                # Exact consumer expression; a literal width is never rewritten.
                expected = relative(reference.replace('.wmp.fits', f'.w{calibration_width}wmp.fits'))
                if under(self.output, expected) == under(self.output, path): return None
            key = f'{int(row["DSNO"])}:{STEPS[3]}:{width}'
            result = dict(id=key, dsno=str(int(row['DSNO'])), step=STEPS[3], label=LABELS[3],
                          status='NotRequired', outputs=[dict(path=str(path), status='NotRequired')],
                          dependencies=[], reasons=[
                              'Not required: no CSV WAVMAP references this output at the configured wavelength-calibration width.',
                              'WLFLAT requires its fiber trace and extracted spectrum, not its own wavelength map. '
                              'Wavelength calibration uses the WAVMAP reference; this optional step can still be run explicitly.'])
            self.nodes[key] = result
            return result
        except (KeyError, ValueError, OSError):
            return None  # Unresolved/malformed references must not be hidden.

    def inspect(self, row):
        selected = [self.unrequired_missing_map(row) or self.node(row, step)
                    if step == STEPS[3] else self.node(row, step) for step in STEPS]
        return {'version': 1, 'dsno': str(int(row['DSNO'])), 'steps': selected,
                'nodes': list(self.nodes.values()), 'notes': self.notes,
                'historicalRuns': self.historical_runs,
                'warningCount': sum(d['severity'] == 'warning' for d in self.diagnostics),
                'diagnostics': self.diagnostics}


def main():
    from tifres_launcher import read_table, select_rows, dsnos
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('script-dir', 'csv', 'raw-dir', 'fits-dir', 'dsno'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--options-json', default='{}')
    args = parser.parse_args()
    _, rows = read_table(args.csv)
    selected = select_rows(rows, dsnos([args.dsno]))
    if len(selected) != 1: raise ValueError('Status requires one selected DSNO.')
    print(json.dumps(Inspector(rows, args.script_dir, args.raw_dir, args.fits_dir, json.loads(args.options_json)).inspect(selected[0]), ensure_ascii=True))


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    try: main()
    except Exception as ex:
        print(f'Status inspection failed: {ex}', file=sys.stderr)
        sys.exit(1)
